#!/usr/bin/env python3

import os
import time
import requests
import datetime
import zipfile
import tarfile
import shutil
import subprocess

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = os.getenv("REPO_OWNER")
REPO_NAME = os.getenv("REPO_NAME")
DOWNLOAD_PATH = "builds"
CHECK_INTERVAL = 30
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

def get_workflow_runs(workflow_name, run_age_days = 7):
    now_time = datetime.datetime.now()
    past_time = now_time - datetime.timedelta(days=run_age_days)
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?per_page=100&created=>{past_time.isoformat()}Z"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()

    workflow_runs = filter(lambda x: x["name"] == workflow_name,
                           response.json().get("workflow_runs", []))

    return list(workflow_runs)

def get_run_artifacts_list(run_id):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs/{run_id}/artifacts"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json().get("artifacts", [])

def repack_archives(build_dir):
    # At the time of creating this script uncompressed _autorun_summary is about 200MB in size
    # That's too much, so let's compress artifacts again, but but as separate archives allowing for
    # easier access to individual files.
    for archive in ["coverage", "ut_coverage", "doc"]:
        archive_path = os.path.join(build_dir, archive)
        archive_file = os.path.join(build_dir, f"{archive}.tar.gz")

        if not os.path.exists(archive_path):
            continue

        subprocess.run(["tar", "-C", archive_path, "-czf", archive_file, '.'])
        print(["tar", "-C", archive_path, "-czf", archive_file, '.'])
        # TODO: There's some difference with how tar files are created by python and by tar command,
        # not sure what are they, but this affects later .tar.gz files consupmtion by tar.js
        # script. Let's use tar for now and revisit in future if tarfile module can be used.
        # with tarfile.open(archive_file, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        #     for file in os.listdir(os.path.join(build_dir, archive)):
        #         tar.add(os.path.join(build_dir, archive, file), arcname=file)
        shutil.rmtree(archive_path)

    # compress common-job-* artifacts back again
    for common_job_dir in os.listdir(build_dir):
        if common_job_dir.startswith("common-job-"):
            common_job_path = os.path.join(build_dir, common_job_dir)
            common_job_archive_path = os.path.join(build_dir, f"{common_job_dir}.tar.gz")
            with tarfile.open(common_job_archive_path, "w:gz") as tar:
                tar.add(common_job_path, arcname=common_job_dir)
            shutil.rmtree(common_job_path)

def download_artifact(artifact):
    run_id = artifact["workflow_run"]["id"]
    build_dir = os.path.join(DOWNLOAD_PATH, str(run_id))
    artifact_name = artifact["name"]
    artifact_url = artifact["archive_download_url"]
    artifact_filename = f"{artifact_name}.zip"
    artifact_path = os.path.join(build_dir, artifact_filename)

    if os.path.exists(build_dir):
        print(f"Directory {build_dir} already exists, skipping download")
        return
    
    os.makedirs(build_dir, exist_ok=True)
    response = requests.get(artifact_url, headers=HEADERS, stream=True)
    response.raise_for_status()

    with open(artifact_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    with zipfile.ZipFile(artifact_path, 'r') as zip_ref:
        zip_ref.extractall(build_dir)

    repack_archives(build_dir)

    os.remove(artifact_path)

def artifact_sanitizer(artifacts_age_days = 7):
    now_time = datetime.datetime.now()
    past_time = now_time - datetime.timedelta(days=artifacts_age_days)
    for run_dir in os.listdir(DOWNLOAD_PATH):
        if "assets" in run_dir:
            continue
        run_dir_path = os.path.join(DOWNLOAD_PATH, run_dir)
        run_dir_time = datetime.datetime.fromtimestamp(os.path.getctime(run_dir_path))
        if run_dir_time < past_time:
            shutil.rmtree(run_dir_path)

def main():
    while True:
        runs = get_workflow_runs("SPDK per-patch tests")
        for run in runs:
            artifacts_list = get_run_artifacts_list(run["id"])
            summary_artifact = next(filter(lambda x: x["name"] == "_autorun_summary", artifacts_list), None)
            if summary_artifact:
                download_artifact(summary_artifact)
        artifact_sanitizer()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    if None in [GITHUB_TOKEN, REPO_OWNER, REPO_NAME]:
        print("Please set GITHUB_TOKEN, REPO_OWNER and REPO_NAME environment variables.")
        exit(1)
    main()
