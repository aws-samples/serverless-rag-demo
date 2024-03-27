import awswrangler as wr
import json 
from decimal import Decimal

def handler(event, context):
    print(event)
    payload = event
    df = None
    try:
            if 's3_prefix' in payload:
                if '.csv' in payload['s3_prefix']:
                    df = wr.s3.read_csv(payload['s3_prefix'], na_values=['null', 'none'], skip_blank_lines=True)
                elif '.xls' in payload['s3_prefix']  or '.xlsx' in payload['s3_prefix']:
                    df = wr.s3.read_excel(payload['s3_prefix'])
                elif 'vnd.openxmlformats' in payload['s3_prefix']:
                    df = wr.s3.read_excel(payload['s3_prefix'])
                elif '.json' in payload['s3_prefix']:
                    df = wr.s3.read_json(payload['s3_prefix'])
                else:
                    df = wr.s3.read_fwf(payload['s3_prefix'])
                return {
                            'statusCode': '200',
                            'body': df.to_string(),
                            'headers': {
                                     "Access-Control-Allow-Origin": "*",
                                     "Content-Type": "application/json",
                                     "Access-Control-Allow-Methods": "*",
                                     "Access-Control-Allow-Headers": "Content-Type",
                                     "Access-Control-Allow-Credentials": "*"
                           },
                        }
    except Exception as e:
        return {
                            'statusCode': '400',
                            'body': json.dumps(e),
                            'headers': {
                                     "Access-Control-Allow-Origin": "*",
                                     "Content-Type": "application/json",
                                     "Access-Control-Allow-Methods": "*",
                                     "Access-Control-Allow-Headers": "Content-Type",
                                     "Access-Control-Allow-Credentials": "*"
                           },
                        }
        