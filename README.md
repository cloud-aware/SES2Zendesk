# SEStoZendesk
Use AWS SES, S3, and Lambda to create Zendesk tickets via the API from emails

fork of: [https://gist.github.com/ninajlu/d0b939ee34257fe2b21ae935321895d3](https://gist.github.com/ninajlu/d0b939ee34257fe2b21ae935321895d3)

Create SES Ruleset to [deliver incoming email to an S3 bucket ](https://docs.aws.amazon.com/ses/latest/dg/receiving-email-action-s3.html)

Create Lambda trigger
![image](https://github.com/cloud-aware/SEStoZendesk/assets/38328249/e61a2907-668c-4502-9987-1cf1a514f27d)

Make sure the Lambda function has permissions to the proper KMS key holding the zendesk token, & the S3 bucket where SES stores the email

