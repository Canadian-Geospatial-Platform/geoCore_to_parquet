import io
import json
import logging
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from botocore.exceptions import ClientError
import boto3

def lambda_handler(event, context):
    """
    AWS Lambda Entry
    """
    print(event)
    
    """PROD SETTINGS"""
    bucket_parquet = "redacted"
    region = "ca-central-1"
    s3_paginate_options = {'Bucket':'redacted'} # Python dict, seperate with a comma: {'StartAfter'=2018,'Bucket'='demo'} see: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.list_objects_v2
    s3_geocore_options = {'Bucket':'redacted'}

    """ 
    Used for `sam local invoke -e payload.json` for local testing
    For actual use, comment out the two lines below 
    """
    
    #if "body" in event:
    #    event = json.loads(event["body"])
    
    """ 
    Parse query string parameters 
    """
    
    try:
        verbose = event["queryStringParameters"]["verbose"]
    except:
        verbose = False
        
    """
    Convert JSON files in the input bucket to parquet
    """
    
    #list all files in the s3 bucket
    filename_list = s3_filenames_paginated(region, **s3_paginate_options)
    
    #for each json file, open for reading, add to dataframe (df), close
	#todo exception handling
    result = []
    count = 0
    for file in filename_list:
        body = open_s3_file(file, **s3_geocore_options)
        json_body = json.loads(body)
        result.append(json_body)
        count += 1
        if (count % 500) == 0:
            print (count)
            temp_file = "records" + str(count) + ".json"
            temp_parquet_file = "records" + str(count) + ".parquet"
            
			#normalize the geocore 'features' array
            df = pd.json_normalize(result, 'features', record_prefix='features_')
            df.columns = df.columns.str.replace(r".", "_") #parquet does not support characters other than underscore
            
            """debug"""
            print(df.dtypes)
            print(df.head())
            
			#convert the appended json files to parquet format
            df.to_parquet(temp_parquet_file)
			
			
			#upload the appended json file to s3
            upload_json_stream(temp_file, bucket_parquet, str(result))
			#upload parquet file to s3
            upload_file(temp_parquet_file, bucket_parquet)
            
            #clear result and dataframe
            result = []
            df = pd.DataFrame(None)
			
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "todo: hello world",
            }
        ),
    }
    
def s3_filenames_paginated(region, **kwargs):
    """Paginates a S3 bucket to obtain file names. Pagination is needed as S3 returns 999 objects per request (hard limitation)
    :param region: region of the s3 bucket 
    :param kwargs: Must have the bucket name. For other options see the list_objects_v2 paginator: 
    :              https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.list_objects_v2
    :return: a list of filenames within the bucket
    """
    client = boto3.client('s3', region_name=region)
    
    paginator = client.get_paginator('list_objects_v2')
    result = paginator.paginate(**kwargs)
    
    filename_list = []
    count = 0
    
    for page in result:
        if "Contents" in page:
            for key in page[ "Contents" ]:
                keyString = key[ "Key" ]
                #print(keyString)
                count += 1
                filename_list.append(keyString)
    
    print (count)
                
    return filename_list
    
def open_s3_file(filename, **kwargs):
    """Open a S3 file from bucket_name and filename and return the body as a string
    :param bucket_name: Bucket name
    :param filename: Specific file name to open
    :return: body of the file as a string
    """
    
    """
    Buffer to memory. Faster but memory intensive: https://stackoverflow.com/a/56814926
    """
    
    try:
        client = boto3.client('s3')
        bytes_buffer = io.BytesIO()
        client.download_fileobj(Key=filename, Fileobj=bytes_buffer, **kwargs)
        file_body = bytes_buffer.getvalue().decode() #python3, default decoding is utf-8
        #print (file_body)
        return str(file_body)
    except ClientError as e:
        logging.error(e)
        return False

    """
    Potentially slower

    try:
        s3_resource = boto3.resource('s3')
        obj = s3_resource.get_object(Key=filename, Bucket=bucket_name)
        file_body = obj.get()['Body'].read().decode('utf-8')
        print (file_body)
        return file_body
    except ClientError as e:
        logging.error(e)
        return False
    """

def upload_json_stream(file_name, bucket, json_data, object_name=None):
    """Upload a json file to an S3 bucket
    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param json_data: stream of json data to write
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = file_name

    # Upload the file
    s3 = boto3.resource('s3')
    try:
        s3object = s3.Object(bucket, file_name)
        response = s3object.put(Body=(bytes(json.dumps(json_data, indent=4, ensure_ascii=False).encode('utf-8'))))
    except ClientError as e:
        logging.error(e)
        return False
    return True
    
def upload_file(file_name, bucket, object_name=None):
    """Upload a file to an S3 bucket
    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = file_name

    # Upload the file
    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True