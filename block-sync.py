#! `env`/python
"""
# Block Sync

Read a collection of remote sites block list and dump out a
mastodon 4.1 compatible `domain_blocks.csv` file. Optionally
this will also add them to your own instance.

## Notes:

If you want to use the --update_home option, you'll need to
add a permission to the owner of the API_KEY.
In the database:

```postgres
UPDATE oauth_access_tokens
    SET scopes='admin:write:domain_blocks'
    WHERE token='_YourAppKeyHere_';
```

"""

from io import FileIO
import logging
import json
import re
from urllib.parse import urlencode

import requests
import configargparse


VERSION = "1.0.0"


def config():
    """read in the configuration."""
    parser = configargparse.ArgParser(
        default_config_files=["settings.conf"],
        description=f"""Read a collection of remote sites block list and dump out a
mastodon 4.1 compatible `domain_blocks.csv` file. Optionally
this will also add them to your own instance. Version {VERSION}""",
    )
    parser.add("-c", "--config", is_config_file=True, help="config file path")
    parser.add("-v", "--verbose", action="store_true", help="verbose mode")
    parser.add("-q", "--quiet", action="store_true", help="only report errors")
    parser.add("--app_key", help="your server's access key", env_var="APP_KEY")
    parser.add("--dry_run", action="store_true", help="just fetch and compare")
    parser.add(
        "--allow",
        default="allow.lst",
        help="always allow the sites listed in this file, separated by new lines",
    )
    parser.add(
        "--output",
        default="domain_blocks.csv",
        env_var="OUTPUT",
        help="dump the collected list of sites to specified file",
    )
    parser.add("--home", help="your instance url", env_var="HOME_HOST")
    parser.add(
        "--log_level",
        default="error",
        env_var="LOGGING",
        help="logging level [debug,info,warn,error]",
    )
    parser.add(
        "--remote",
        nargs="+",
        help="remote servers to fetch from",
        env_var="REMOTE_HOST",
    )
    # parser.add("--process", help="process a JSON file")
    settings = parser.parse_args()
    return settings


def merge(old: dict[str, dict], data: list[dict], origin: str) -> dict[str, dict]:
    """merge the new data set into the collection we've got so far"""
    for item in data:
        if not item.get("domain") or not item.get("severity"):
            raise Exception("data missing required elements")
        if "*" in item.get("domain"):
            continue
        if origin:
            item["private_comment"] = f"from: {origin}"
        old[item.get("domain")] = item
    return old


def fetch(sites: list[str]) -> dict[str, dict]:
    """fetch remote block list using the Public API"""
    result = {}
    block_list_template = "https://{site}/api/v1/instance/domain_blocks"
    for site in sites:
        logging.info("Fetching {site}".format(site=site))
        url = block_list_template.format(site=site)
        logging.debug(url)
        response = requests.get(block_list_template.format(site=site))
        if response.status_code != 200:
            logging.error("🚨{site} not publishing block list".format(site=site))
            continue
        try:
            result = merge(result, response.json(), site)
        except Exception as ex:
            logging.warning("⚠ Merge Exception: {ex}, continuing...".format(ex=ex))
            continue
    logging.debug("{}: {} sites".format(site, len(result)))
    return result


def compare(
    mine: dict[str, dict], theirs: dict[str, dict], allow: list[str]
) -> dict[str, dict]:
    """find what we haven't added yet

    Compare both keys against each other because domains can
    be shorter than we expect (e.g. foo.example.com vs example.com)
    """
    logging.info("Generating differences")
    missing = {}
    for key in theirs.keys():
        if key in allow:
            logging.info(f"skipping allowed {key}")
            continue
        use = True
        for mkey in mine:
            if key.endswith(mkey) or mkey.endswith(key):
                if mkey != key:
                    logging.debug(f"{mkey} == {key}")
                use = False
                break
        if use:
            missing[key] = theirs[key]
            logging.debug(f"++ {key}")
    logging.info(f"Found {len(missing)} new sites")
    logging.debug(missing)
    return missing


def apply_diff(home: str, auth: str, diff: dict[str, dict]):
    """Add the domains we've not seen yet to our instance."""
    logging.info("Applying differences to home site")
    url = f"https://{home}/api/v1/admin/domain_blocks"
    creds = f"Bearer {auth}"
    for key in diff.keys():
        data = diff.get(key)
        args = {
            "domain": key,
            "severity": data.get("severity", "suspend"),
            "private_comment": data.get("private_comment"),
        }
        if diff.get(key).get("comment"):
            args["comment"] = diff.get(key).get("comment")
        body = urlencode(args)
        logging.debug(body)
        resp = requests.post(url=url, headers={"Authorization": creds}, data=body)
        if resp.status_code == 422:
            logging.warning(resp.text)
            continue
        if resp.status_code != 200:
            raise Exception(
                "Error updating blocks: {}:{}".format(resp.status_code, resp.text)
            )
    logging.info("Changes applied.")


def get_log_level(args) -> int:
    """Since match isn't availabe until 3.10"""
    result = logging.INFO
    level = args.log_level.strip().upper()
    try:
        result = logging._nameToLevel.get(level, logging.INFO)
    except Exception as ex:
        print(ex)
    if args.quiet:
        result = logging.CRITICAL
    if args.verbose:
        result = logging.DEBUG
    return result


def dump_csv(f: FileIO, sites_data: dict[str, dict], allow: list):
    """Dump the list as a Mastodon 4.1 compatible CSV.

    The `private_comment` may not import, but will show the origin of the block.
    """
    f.write(
        "#domain,#severity,#reject_media,#reject_reports,#public_comment,#obfuscate\n"
    )
    for site, data in sorted(sites_data.items(), key=lambda t: t[0]):
        if site in allow:
            logging.info(f"skipping allowed {site}")
            continue
        severity = data.get("severity") or "silence"
        row = [
            site,
            data.get("severity") or "silence",
            data.get("reject_media") or "{}".format(severity == "suspend").lower(),
            data.get("reject_report") or "{}".format(severity == "suspend").lower(),
            '"{}"'.format(re.sub("([\"'])", r"\\\1", data.get("comment") or "")),
            "false",
        ]
        f.write(",".join(row) + "\n")


def main():
    args = config()
    level = get_log_level(args)
    logging.basicConfig(encoding="utf-8", level=level)
    my_data = {}
    logging.info("Collecting public block lists")
    sites_data = fetch(args.remote)
    allow = []
    if args.allow:
        try:
            with open(args.allow, "r") as f:
                allow = [x.strip() for x in f.read().split("\n")]
        except FileNotFoundError as e:
            pass
    if args.output:
        logging.info(f"Outputing collected blocks to {args.output}")
        with open(args.output, "w") as f:
            dump_csv(f, sites_data, allow)
    if args.home:
        my_data = fetch([args.home])
        diff = compare(my_data, sites_data, allow)
        if not args.dry_run:
            if not args.app_key:
                raise Exception(
                    "Missing `app_key` argument. Can't update home instance."
                )
            apply_diff(args.home, args.app_key, diff)
    if args.dry_run:
        print(json.dumps(diff, indent=2))


main()