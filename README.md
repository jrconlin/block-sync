# Block Sync

A mastodon admin tool to sync block lists between instances.

## Introduction

I run a small instance. I don't get much crap traffic, but it would be nice to be able to pre-emptively block a-holes before they show up. To do that, I
pull the block lists from a set of trusted servers and then add those sites to mine.

## How To

This is a work in progress, possibly zeta level code, so, you know.

You can specify options using the CLI, Environment, or a static file in `settings.config`.

This will grab the public block lists using the HTTP API for the sites listed in `--remote`. It then generates a Mastodon compatible block file
(default: `domain_blocks.csv`). If you specify the `--home {HOST}`, it will attempt to import the blocks directly into your server.

For example:

```bash
python block_sync.py --remote hachyderm.io --remote infosec.exchange --output my_blocklist.csv
```

will fetch block lists from https://hacyderm.io, and https://infosec.exchange, and write out the bocks to `my_blocklist.csv`

This uses python, so simple python setup rules apply.
e.g.

```bash
$ python3 -mvenv venv
$ exec venv/bin/activate
(venv)$ pip install -r requirements.txt
```

## Setup

This version will output a `domain_blocks.csv` file that you can import into your instance. A sample `settings.conf.sample` is provided. If you wish to use it, please rename it to `settings.conf`

The older interface still exists, and can write the domains into your instance, but some extra steps are still requrired. Surprisingly, while there's an HTTP API to add sites, the permission to add them is not readily available to applications. You will need to access the database and manually set the token's permission.

```postgres
UPDATE oauth_access_tokens
    SET scopes='admin:write:domain_blocks'
    WHERE token='_YourAppKeyHere_';
```
