from urllib.request import urlopen
import boto3
import io
import json
import logging
import uuid
import os
from urllib import parse
from botocore.client import Config
from botocore.exceptions import ClientError as S3ClientError
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig            
import datetime      

# # Set up logging
logger = logging.getLogger(__name__)
logger.setLevel('INFO')

# Enable Verbose logging for Troubleshooting
# boto3.set_stream_logger("")                  

# Define Environmental Variables
my_root_url = str(os.environ['root_url'])
my_max_attempts = int(os.environ['max_attempts'])
my_max_pool_connections = int(os.environ['max_pool_connections'])
my_max_concurrency = int(os.environ['max_concurrency'])            
my_region = str(os.environ['AWS_REGION'])
obj_copy_storage_class = str(os.environ['copy_storage_class'])
my_multipart_chunksize = int(os.environ['multipart_chunksize'])
my_multipart_threshold = int(os.environ['multipart_threshold'])
my_checksum_type = str(os.environ['checksum_type'])                 


# Set and Declare Configuration Parameters
upload_transfer_config = TransferConfig(max_concurrency=my_max_concurrency,
                                        multipart_chunksize=my_multipart_chunksize,
                                        multipart_threshold=my_multipart_threshold,
                                        )
config = Config(max_pool_connections=my_max_pool_connections, retries={'max_attempts': my_max_attempts})

# Set and Declare Copy Arguments
my_upload_args = {'ACL': 'bucket-owner-full-control', 'StorageClass': obj_copy_storage_class, 'ChecksumAlgorithm' : my_checksum_type}

# Set Service Clients
s3 = boto3.resource('s3', config=config, region_name=my_region)

# Stream Downloaded file from URL to Support Tool Amazon S3 Bucket
def stream_to_s3(url, bucket, key):
    logger.info(f'Starting the streaming of object in URL to the S3 Bucket: s3://{bucket}/{key}')
    try:
        with urlopen(url) as inv_stream:
            s3.Object(bucket, key).upload_fileobj(inv_stream,
                                                  Config=upload_transfer_config,
                                                  ExtraArgs=my_upload_args,
                                                  )                                        
    except Exception as e:
        logger.error(e)
        raise e
    else:
        logger.info(f'Object successfully uploaded to s3://{bucket}/{key}')



def lambda_handler(event, context):
  # Parse job parameters from Amazon S3 batch operations
  jobId = event['job']['id']
  invocationId = event['invocationId']
  invocationSchemaVersion = event['invocationSchemaVersion']

  # Prepare results
  results = []

  # Parse Amazon S3 Key, Key Version, and Bucket ARN
  taskId = event['tasks'][0]['taskId']
  # use unquote_plus to handle various characters in S3 Key name
  s3Key = parse.unquote_plus(event['tasks'][0]['s3Key'], encoding='utf-8')
  s3BucketArn = str(event['tasks'][0]['s3BucketArn'])
  s3Bucket = s3BucketArn.split(':')[-1]
  # Create assest full url path
  url_path = parse.quote(s3Key)
  my_asset_url = f"{my_root_url}/{url_path}"
  logger.info(f"My full URL path is {my_asset_url}")     

  try:
    # Prepare result code and string
    resultCode = None
    resultString = None
    # Remove line feed or carriage return for compatibility with S3 Batch Result Message
    # Will use str.translate to strip '\n' and '\r'. Convert both char to ascii using ord()
    # where '\t' = 9, '\n' = 10 and '\r' = 13
    mycompat = {9: None, 10: None, 13: None}

    # Initialize response to Batch Operations

    # Initialize Stream from URL and upload to Amazon S3 Bucket
    stream_to_s3(my_asset_url, s3Bucket, s3Key)                
    # Mark as succeeded
    resultCode = 'Succeeded'
    resultString = str("Successfully completed the copy process!")                

  except Exception as e:
    # log errors, some errors does not have a response, so handle them
    logger.error(f"Unable to complete requested operation, see Additional Client/Service error details below:")
    try:
      logger.error(e.response)
      errorCode = e.response.get('Error', {}).get('Code')
      errorMessage = e.response.get('Error', {}).get('Message')
      errorS3RequestID = e.response.get('ResponseMetadata', {}).get('RequestId')
      errorS3ExtendedRequestID = e.response.get('ResponseMetadata', {}).get('HostId')
      resultString = '{}: {}: {}: {}'.format(errorCode, errorMessage, errorS3RequestID, errorS3ExtendedRequestID)
    except AttributeError:
      logger.error(e)
      resultString = 'Exception: {}'.format(str(e).translate(mycompat))
    resultCode = 'PermanentFailure'

  finally:
    results.append({
    'taskId': taskId,
    'resultCode': resultCode,
    'resultString': resultString
    })

  return {
  'invocationSchemaVersion': invocationSchemaVersion,
  'treatMissingKeysAs': 'PermanentFailure',
  'invocationId': invocationId,
  'results': results
  }
