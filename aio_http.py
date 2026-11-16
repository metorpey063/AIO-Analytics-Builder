"""
aio_http.py — `requests` with a default timeout.

Use it exactly like requests:

    import aio_http as requests          # or: import aio_http as req
    r = requests.get(url, headers=h)

`requests` has no timeout unless every call passes one, and most of AIO's calls don't, so an
API that stops answering would hold a build thread forever. Here a call without `timeout=`
gets DEFAULT_TIMEOUT; a call that passes its own (including `timeout=None`) keeps it.

Nothing else changes: each call still opens its own connection, as `requests.get()` does
(no shared session, no cookies carried between calls, no retries). Everything that isn't a
request function (`exceptions`, `RequestException`, `HTTPError`, `utils`, ...) is `requests`'s own.
"""

import requests as _requests

# (connect, read) seconds. Read is the gap allowed between bytes of a response, not the whole
# call. 10 minutes is Salesforce's own ceiling for a synchronous request, so nothing that
# completes today is cut short; a call that would have hung forever now fails after 10 minutes.
DEFAULT_TIMEOUT = (15, 600)


def request(method, url, **kwargs):
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return _requests.request(method, url, **kwargs)


def get(url, params=None, **kwargs):
    return request("get", url, params=params, **kwargs)


def post(url, data=None, json=None, **kwargs):
    return request("post", url, data=data, json=json, **kwargs)


def put(url, data=None, **kwargs):
    return request("put", url, data=data, **kwargs)


def patch(url, data=None, **kwargs):
    return request("patch", url, data=data, **kwargs)


def delete(url, **kwargs):
    return request("delete", url, **kwargs)


def head(url, **kwargs):
    kwargs.setdefault("allow_redirects", False)   # as requests.head does
    return request("head", url, **kwargs)


def options(url, **kwargs):
    return request("options", url, **kwargs)


def __getattr__(name):
    """exceptions, RequestException, HTTPError, utils, codes, Session, ... straight from requests."""
    return getattr(_requests, name)
