import hashlib
from pathlib import Path

import boto3


def assume_role_session(role_arn: str):
    if not role_arn:
        return boto3.Session()
    sts = boto3.client("sts")
    creds = sts.assume_role(RoleArn=role_arn, RoleSessionName="cur-downloader")["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_cur_file(manifest, s3_key: str, local_path: Path) -> str:
    session = assume_role_session(manifest.account.iam_role_arn)
    s3 = session.client("s3", region_name=manifest.aws_region)
    s3.download_file(manifest.s3_bucket, s3_key, str(local_path))
    return sha256_of_file(local_path)
