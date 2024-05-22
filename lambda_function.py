from __future__ import print_function

import json
import boto3
import time
import urllib
import requests
import re
import mimetypes
import base64
import os

# Purpose: Accept email from SES (defined in SES rule), SES writes email to S3 Bucket, Lambda has a trigger on new objects being put in S3 bucket.
#          Lambda function calls appropriate Zendesk instance and creates ticket with details from the email.  Zendesk token is stored in KMS.
# Modification of: https://gist.github.com/ninajlu/d0b939ee34257fe2b21ae935321895d3 / https://medium.com/@ninajlu/using-aws-lambda-s3-to-automatically-create-zendesk-tickets-from-looker-scheduled-reports-816c45e2fbb3

# Import the email modules we'll need
from email import policy
from email.parser import Parser

# Get the service resource
s3 = boto3.client('s3')
tests3 = boto3.resource(u's3')
emailRegex = r"([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9_-]+)"
nameRegex = r"(?:(\"?(?:.*)\"?)\s)?"

# insert_data function for creating a Zendesk ticket from the data
def insert_data(emailData):
    
    #Set the Body of your Ticket
    html_body = emailData.get_body(preferencelist=('html', 'plain')).get_content()
    attachments = emailData.iter_attachments()
    # print("html_body: ", html_body)
    toEmail = re.search(emailRegex, emailData['to']).group(1)
    # print("toEmail: ", toEmail)
    
    # Create ticket in different zendesk instances based on which mailbox received message
    if toEmail == 'myemail@mydomain.com':
        brand_id = 01234567890123
        zendesk_instance = 'myinstance1'
    elif toEmail == 'myemail2@mydomain.com':
        brand_id = 01234567890124
        zendesk_instance = 'myinstance2'
    elif toEmail == 'myemail3@mydomain.com':
        brand_id = 01234567890125
        zendesk_instance = 'myinstance3'
    else:
        brand_id = 01234567890126 # Catch-all
        zendesk_instance = 'myinstance4'

    subject = emailData['subject']
    #is_public determines whether or not the comment will be internal to your organization or sent to a user.
    is_public = True
    # set tags to identify tickets created by this service
    tags = list()
    # tags.append('Email2APIService') # Append a tag to your tickets for identification purposes

    requesterEmail = re.search(emailRegex, emailData['from']).group(1)
    requesterName = re.search(nameRegex, emailData['from']).group(1)
    
    if not requesterName: # set the requesterName to the requester email if there is no requester name
        requesterName = requesterEmail
        
    # Set the request parameters
    headers = {'content-type': 'application/json'}
    
    # Store the token credential as a Lambda environment variable
    if zendesk_instance == 'myinstance1':
        url = 'https://myinstance1.zendesk.com/api/v2/tickets.json'
        user = 'myuser/token'
        ENCRYPTED = os.environ['myinstance1_token']
        # Decrypt code should run once and variables stored outside of the function
        # handler so that these are decrypted once per container
        DECRYPTED = boto3.client('kms').decrypt(
            CiphertextBlob=base64.b64decode(ENCRYPTED),
            EncryptionContext={'LambdaFunctionName': os.environ['AWS_LAMBDA_FUNCTION_NAME']}
        )['Plaintext'].decode('utf-8')
    else:
        url = 'https://myinstance2.zendesk.com/api/v2/tickets.json'
        user = 'myuser/token'
        ENCRYPTED = os.environ['myinstance2_token']
        # Decrypt code should run once and variables stored outside of the function
        # handler so that these are decrypted once per container
        DECRYPTED = boto3.client('kms').decrypt(
            CiphertextBlob=base64.b64decode(ENCRYPTED),
            EncryptionContext={'LambdaFunctionName': os.environ['AWS_LAMBDA_FUNCTION_NAME']}
        )['Plaintext'].decode('utf-8')

    # Upload Attachments
    if attachments:
        attach_upload = list()
        for attachment in attachments:
            # print("attachment: ", attachment)
            attach_filename =  attachment.get_filename()
            attach_header = {'content-type': attachment.get_content_type()}
            # print("attach_filename: ", attach_filename)
            # print("attach_type: ", attach_header)
            attachurl = 'https://' + zendesk_instance + '.zendesk.com/api/v2/uploads?filename=' + attach_filename
            # print("attachurl: ", attachurl)
            attachfile = attachment.get_content()
            # print("attachfile: ", attachfile)
            attach_response = requests.post(attachurl, data=attachfile, auth=(user, DECRYPTED), headers=attach_header)
            attach_response_json = json.loads(attach_response.text)
            # print("attach_response: ", json.dumps(attach_response_json))
            # print("upload token debug: ", attach_response_json['upload']['token'])
            attach_upload.append(attach_response_json['upload']['token'])
        # print("attach_upload list: ", attach_upload)
        attach_data = {'ticket': {'brand_id': brand_id, 'subject': subject, 'tags': tags, 'is_public': is_public, 'comment': {'uploads': attach_upload, 'public': is_public, 'html_body': html_body}, 'requester': { 'name': requesterName, 'email': requesterEmail } }}
        attach_payload = json.dumps(attach_data)
        response = requests.post(url, data=attach_payload, auth=(user, DECRYPTED), headers=headers)
    else:
        data = {'ticket': {'brand_id': brand_id, 'subject': subject, 'tags': tags, 'is_public': is_public, 'comment': {'public': is_public, 'html_body': html_body}, 'requester': { 'name': requesterName, 'email': requesterEmail } }}
        # Create a JSON payload
        payload = json.dumps(data)
        # Do the HTTP post request w/out attachments
        response = requests.post(url, data=payload, auth=(user, DECRYPTED), headers=headers)

    # Check for HTTP codes other than 201 (Created)
    if response.status_code != 201:
        print('Status:', response.status_code, 'Problem with the request. Exiting.')
        exit()

    # Report success
    print('Successfully created the ticket.') 

# lambda_handler is the main function in lambda function
def lambda_handler(event,context):
    print("event: ", event)
    source_bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    copy_source = {'Bucket':source_bucket , 'Key':key}
    
    try:
        bucket = tests3.Bucket(source_bucket)
        obj = bucket.Object(key=key)
        response = obj.get()
        print("response from file object")
        print(response)
        # lines = response['Body'].read().decode('utf-8').splitlines(True)
        emailBody = response['Body'].read().decode('utf-8')
        # msg = BytesParser(policy=policy.default).parse(emailBody)
        msg = Parser(policy=policy.default).parsestr(emailBody)
        
        # print("msg details")
        # print('To:', msg['to'])
        # print('From:', msg['from'])
        # print('Subject:', msg['subject'])        

        # print("emailBody: ", emailBody)
        # print(emailBody)
        insert_data(msg)
        s3.delete_object(Bucket=source_bucket, Key=key) # Delete the object from S3 - comment this out if you want to keep it
        
    except Exception as e:
        print(e)
        print('Error getting object {} from bucket {}. Make sure they exist and your bucket is in the same region as this function.'.format(key, source_bucket))
        raise e
