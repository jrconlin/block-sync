#! `env`/python
"""
# Block Sync

Read a collection of remote sites block list and add them to
your own instance.

## Notes:

You'll need to add a permission to the owner of the API_KEY.
In the database:

```postgres
UPDATE oauth_access_tokens
    SET scopes='admin:write:domain_blocks'
    WHERE token='_YourAppKeyHere_';
```

"""

import logging
import json
from urllib.parse import urlencode

import requests
import configargparse


def config():
    """read in the configuration."""
    parser = configargparse.ArgParser(default_config_files=["settings.conf"])
    parser.add("-c", "--config", is_config_file=True, help="config file path")
    parser.add("-v", "--verbose", action="store_true", help="verbose mode")
    parser.add("-q", "--quiet", action="store_true", help="only report errors")
    parser.add("--app_key", help="your server's access key", env_var="APP_KEY")
    parser.add("--dry_run", action="store_true", help="just fetch and compare")
    parser.add("--dump", help="dump the collected list of sites to specified file")
    parser.add("--home", required=True, help="your instance url", env_var="HOME_HOST")
    parser.add("--load", help="load the collected list of sites from specified file")
    parser.add("--whitelist", help="allways allow these sites")
    parser.add(
        "--log_level", default="info", help="logging level [debug,info,warn,error]"
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


def merge(old: dict[str, dict], data: list[dict], site: str) -> dict[str, dict]:
    """merge the new data set into the collection we've got so far"""
    for item in data:
        if not item.get("domain") or not item.get("severity"):
            raise Exception("data missing required elements")
        if "*" in item.get("domain"):
            continue
        old[item.get("domain")] = {
            "severity": item.get("severity"),
            "comment": item.get("comment"),
            "site": site,
        }
    return old


def fetch(sites: list[str]) -> dict[str, dict]:
    """fetch remote blocl list"""
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
            result = merge(result, response.json(), site)
        except Exception as ex:
            logging.error("Exception: {ex}".format(ex=ex))
            continue
    logging.debug("{}: {} sites".format(site, len(result)))
    return result


def compare(
    mine: dict[str, dict], theirs: dict[str, dict], whitelist: list[str]
) -> dict[str, dict]:
    """find what we haven't added yet

    Compare both keys against each other because domains can
    be shorter than we expect (e.g. foo.example.com vs example.com)
    """
    missing = {}
    for key in theirs.keys():
        if key in whitelist:
            logging.info(f"skipping whitelisted {key}")
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
    url = f"https://{home}/api/v1/admin/domain_blocks"
    creds = f"Bearer {auth}"
    for key in diff.keys():
        args = {
            "domain": key,
            "severity": diff.get(key).get("severity"),
            "private_comment": "from: " + diff.get(key).get("site"),
        }
        if diff.get(key).get("comment"):
            args["comment"] = diff.get(key).get("comment")
        if diff.get(key).get("site"):
            args["private_comment"] = "from: " + diff.get(key).get("site")
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


def main():
    args = config()
    level = get_log_level(args)
    logging.basicConfig(encoding="utf-8", level=level)
    logging.debug(logging.getLevelName(level))
    my_data = fetch([args.home])
    # TODO: cache data to files
    if args.load:
        with open(args.load, "r") as f:
            sites_data = json.loads(f.read())
    else:
        sites_data = fetch(args.remote)
    if args.dump:
        with open(args.dump, "w") as f:
            f.write(json.dumps(sites_data))
        return
    whitelist = []
    if args.whitelist:
        with open(args.whitelist, "r") as f:
            whitelist = [x.strip() for x in f.read().split("\n")]
    diff = compare(my_data, sites_data, whitelist)
    if diff:
        if not args.dry_run:
            apply_diff(args.home, args.app_key, diff)
        else:
            print(json.dumps(diff, indent=2))


main()
