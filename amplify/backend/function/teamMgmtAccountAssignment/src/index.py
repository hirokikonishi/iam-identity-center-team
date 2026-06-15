# © 2023 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.
# This AWS Content is provided subject to the terms of the AWS Customer Agreement available at
# http: // aws.amazon.com/agreement or other written agreement between Customer and either
# Amazon Web Services, Inc. or Amazon Web Services EMEA SARL or both.
import os
import boto3
from botocore.exceptions import ClientError

MGMT_CROSS_ACCOUNT_ROLE_ARN = os.environ.get("MGMT_CROSS_ACCOUNT_ROLE_ARN", "")
REGION = os.environ.get("REGION", os.environ.get("AWS_REGION", "ap-northeast-1"))


def get_mgmt_account_id():
    try:
        response = boto3.client("organizations").describe_organization()
        return response["Organization"]["MasterAccountId"]
    except ClientError as e:
        print(f"Error getting management account ID: {e}")
        raise RuntimeError(f"Failed to determine management account ID: {e}") from e


mgmt_account_id = get_mgmt_account_id()


def get_sso_client(account_id):
    """Return SSO client; assumes cross-account role when target is the management account."""
    if account_id == mgmt_account_id:
        if not MGMT_CROSS_ACCOUNT_ROLE_ARN:
            raise ValueError(
                "MGMT_CROSS_ACCOUNT_ROLE_ARN is not configured. "
                "Set the Lambda env var to the IAM role ARN in the management account."
            )
        creds = boto3.client("sts").assume_role(
            RoleArn=MGMT_CROSS_ACCOUNT_ROLE_ARN,
            RoleSessionName="TEAM-MgmtAccountAssignment",
        )["Credentials"]
        return boto3.client(
            "sso-admin",
            region_name=REGION,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
    return boto3.client("sso-admin", region_name=REGION)


def handler(event, context):
    action = event["action"]  # "grant" or "revoke"
    account_id = event["accountId"]

    print(f"action={action} accountId={account_id} isMgmt={account_id == mgmt_account_id}")

    sso = get_sso_client(account_id)
    params = {
        "InstanceArn": event["instanceARN"],
        "PermissionSetArn": event["roleId"],
        "PrincipalId": event["userId"],
        "PrincipalType": "USER",
        "TargetId": account_id,
        "TargetType": "AWS_ACCOUNT",
    }

    if action == "grant":
        response = sso.create_account_assignment(**params)
        status = response.get("AccountAssignmentCreationStatus", {})
        print(f"CreateAccountAssignment status: {status}")
        if status.get("Status") == "FAILED":
            raise RuntimeError(
                f"CreateAccountAssignment failed: {status.get('FailureReason', 'unknown')}"
            )
        return response
    else:
        response = sso.delete_account_assignment(**params)
        status = response.get("AccountAssignmentDeletionStatus", {})
        print(f"DeleteAccountAssignment status: {status}")
        if status.get("Status") == "FAILED":
            raise RuntimeError(
                f"DeleteAccountAssignment failed: {status.get('FailureReason', 'unknown')}"
            )
        return response
