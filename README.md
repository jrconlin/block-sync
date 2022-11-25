# Block Sync

A mastodon admin tool to sync block lists between instances.

## Introduction

I run a small instance. I don't get much crap traffic, but it would be nice to be able to pre-emptively block a-holes before they show up. To do that, I
pull the block lists from a set of trusted servers and then add those sites to mine.

## How To

This is a work in progress, possibly zeta level code, so, you know. 

You can specify options using the CLI, Environment, or a static file in `settings.config`.

It will grab your block list, then grab the public block lists using the HTTP API. It then adds any hosts that are not included in your local block list using your local server API. (see Setup below)

This uses python, so simple python setup rules apply. 
e.g.

```bash 
$ python3 -mvenv venv
$ exec venv/bin/activate
(venv)$ pip install -r requirements.txt
```

## Setup

Surprisingly, while there's an HTTP API to add sites, the permission to add them is not readily available to applications. You will need to access the database and manually set the token's permission.

```postgres
UPDATE oauth_access_tokens
    SET scopes='admin:write:domain_blocks'
    WHERE token='_YourAppKeyHere_';
```
