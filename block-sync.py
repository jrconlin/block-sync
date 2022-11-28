#! `env`/python
"""
# Block Sync

Read a collection of remote sites block list and add them to
your own instance.

## Notes:

"""

import logging
from urllib.parse import urlencode

import requests
import configargparse


def config():
    """read in the configuration."""
    parser = configargparse.ArgParser(default_config_files=["settings.conf"])
    parser.add("-c", "--config", is_config_file=True, help="config file path")
    parser.add("-v", "--verbose", action="store_true", help="verbose mode")
    parser.add("--app_key", help="your server's access key", env_var="APP_KEY")
    parser.add(
        "--home", required=True, help="your instance url",
        env_var="HOME_HOST")
    parser.add(
        "--remote", nargs="+", help="remote servers to fetch from",
        env_var="REMOTE_HOST")
    # parser.add("--process", help="process a JSON file")
    settings = parser.parse_args()
    return settings


def merge(old: dict[str, dict], data: list[dict]) -> dict[str, dict]:
    for item in data:
        if not item.get("domain") or not item.get("severity"):
            raise Exception("data missing required elements")
        if '*' in item.get("domain"):
            continue
        old[item.get("domain")] = {
            "severity": item.get("severity"),
            "comment": item.get("comment")
        }
    return old


def fetch(sites):
    result = {}
    block_list_template = "https://{site}/api/v1/instance/domain_blocks"
    for site in sites:
        logging.info("Fetching {site}".format(site=site))
        url = block_list_template.format(site=site)
        logging.debug(url)
        response = requests.get(block_list_template.format(site=site))
        if response.status_code != 200:
            logging.error("{site} not publishing block list".format(site=site))
            continue
        try:
            result = merge(result, response.json())
        except Exception as ex:
            logging.error("Exception: {ex}".format(ex=ex))
            continue
    logging.debug("{}: {} sites".format(site, len(result)))
    return result


def compare(mine, theirs):
    missing = {}
    for key in theirs.keys():
        logging.debug(f"{key}")
        if key not in mine:
            missing[key] = theirs[key]
            logging.debug("++")
    return missing


def apply_diff(home, auth, diff):
    url = f"https://{home}/api/v1/admin/domain_blocks"
    creds = f"Bearer {auth}"
    for key in diff.keys():
        args = {
            "domain": key,
            "severity": diff.get(key).get("severity"),
            "comment": diff.get(key).get("comment"),
        }
        body = urlencode(args)
        print(body)
        resp = requests.post(
            url=url,
            headers={
                "Authorization": creds
            },
            data=body
        )
        if resp.status_code == 422:
            logging.warning(resp.text)
            continue
        if resp.status_code != 200:
            raise Exception(
                "Error updating blocks: {}:{}".format(
                    resp.status_code, resp.text)
                )


def main():
    args = config()
    if args.verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(encoding="utf-8", level=level)
    my_data = fetch([args.home])
    # TODO: cache data to files
    sites_data = fetch(args.remote)
    # save_cache("sites.json", sites_data)
    diff = compare(my_data, sites_data)
    # save_cache("diffs.json", diff)
    apply_diff(args.home, args.app_key, diff)


main()
