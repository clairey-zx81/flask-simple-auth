#
# Debatable flask-side auth management
#

from typing import Optional, Callable, Dict, Any
from flask import Flask, request

import datetime as dt
from passlib.context import CryptContext  # type: ignore

import logging
log = logging.getLogger('auth')


# carry data for error Response
class AuthException(BaseException):
    def __init__(self, message: str, status: int):
        self.message = message
        self.status = status

#
# AUTH CONFIGURATION
#


# application
APP: Optional[Flask] = None
CONF: Optional[Dict[str, Any]] = None

# auth token
REALM: Optional[str] = None
SECRET: Optional[str] = None

# password management
PM: Optional[CryptContext] = None
get_user_password: Optional[Callable] = None


def setConfig(app: Flask):
    global APP, CONF, REALM, SECRET, PM, get_user_password
    APP = app
    CONF = app.config
    import re
    realm = CONF.get("FSA_TOKEN_REALM", app.name).lower()
    # tr -cd "[a-z0-9_]" "": is there a better way to do that?
    REALM = "".join(c for c in realm if re.match("[a-z0-9_]", c))
    import random
    import string
    # list of 94 chars, about 6.5 bits per char
    chars = string.ascii_letters + string.digits + string.punctuation
    SECRET = CONF["FSA_TOKEN_SECRET"] if "FSA_TOKEN_SECRET" in CONF else \
        ''.join(random.SystemRandom().choices(chars, k=64))  # > 256 bits
    scheme = CONF.get("FSA_PASSWORD_SCHEME", "bcrypt")
    options = CONF.get("FSA_PASSWORD_OPTIONS", {'bcrypt__default_rounds': 4})
    PM = CryptContext(schemes=[scheme], **options)
    get_user_password = CONF.get("FSA_USER_PASSWORD")


#
# HTTP FAKE AUTH
#
# Just trust a parameter, *only* for local testing.
#
# FSA_FAKE_LOGIN: name of parameter holding the login ("LOGIN")
#
def get_fake_auth():
    assert request.remote_user is None
    assert request.environ["REMOTE_ADDR"] == "127.0.0.1"
    params = request.values if request.json is None else request.json
    user = params.get(CONF.get("FSA_FAKE_LOGIN", "LOGIN"), None)
    # it could check that the user exists in db
    if user is None:
        raise AuthException("missing login parameter", 401)
    log.info(f"LOGIN (param): {user}")
    return user


#
# PASSWORD MANAGEMENT
#
# FSA_PASSWORD_SCHEME: name of password scheme for passlib context
# FSA_PASSWORD_OPTIONS: further options for passlib context
#
# note: passlib bcrypt is Apache compatible
#

# passlib context is a pain, you have to know the scheme name to set its round
# which make it impossible to configure directly.

# verify password
def check_password(user, pwd, ref):
    if not PM.verify(pwd, ref):
        log.debug(f"LOGIN (password): password check failed {user}")
        raise AuthException(f"invalid password for user: {user}", 401)
    else:
        log.debug(f"LOGIN (password): password check succeeded for {user}")


# hash password consistently with above check, can be used by app
def hash_password(pwd):
    return PM.hash(pwd)


# check user password agains database-stored credentials
# raise an exception if not ok, otherwise simply proceeds
def check_db_password(user, pwd):
    ref = get_user_password(user)
    if ref is None:
        log.debug(f"LOGIN (password): no such user ({user})")
        raise AuthException(f"no such user: {user}", 401)
    check_password(user, pwd, ref[0])


#
# HTTP BASIC AUTH
#
def get_basic_auth():
    import base64 as b64
    assert request.remote_user is None
    auth = request.headers.get("Authorization", None)
    log.debug(f"auth: {auth}")
    if auth is None or auth[:6] != "Basic ":
        log.debug(f"LOGIN (basic): unexpected auth {auth}")
        raise AuthException("missing or unexpected authorization header", 401)
    user, pwd = b64.b64decode(auth[6:]).decode().split(':', 1)
    if not request.is_secure:
        log.warning("password authentication over an insecure request")
    check_db_password(user, pwd)
    log.info(f"LOGIN (basic): {user}")
    return user


#
# HTTP PARAM AUTH
#
# User credentials provided from http or json parameters.
#
# FSA_PARAM_USER: parameter name for login ("USER")
# FSA_PARAM_PASS: parameter name for password ("PASS")
#
def get_param_auth():
    assert request.remote_user is None
    params = request.values if request.json is None else request.json
    userp = CONF.get("FSA_PARAM_USER", "USER")
    pwdp = CONF.get("FSA_PARAM_PASS", "PASS")
    user, pwd = params.get(userp, None), params.get(pwdp, None)
    if user is None:
        raise AuthException(f"missing login parameter: {userp}", 401)
    if pwd is None:
        raise AuthException(f"missing password parameter: {pwdp}", 401)
    if not request.is_secure:
        log.warning("password authentication over an insecure request")
    check_db_password(user, pwd)
    log.info(f"LOGIN (param): {user}")
    return user


#
# TOKEN AUTH
#
# The token can be checked locally with a simple hash, without querying the
# database and validating a possibly expensive salted password (+400 ms!).
#
# Its form is: <realm>:<user>:<validity-limit>:<signature>
#
# FSA_TOKEN_NAME: name of parameter holding the token ("auth")
# FSA_TOKEN_HASH: hashlib algorithm for token authentication ("blake2s")
# FSA_TOKEN_LENGTH: number of signature bytes (32)
# FSA_TOKEN_DELAY: token validity in minutes (60)
# FSA_TOKEN_SECRET: signature secret for tokens (mandatory!)
# FSA_TOKEN_REALM: token realm (lc simplified app name)
#

# sign data with secret
def compute_signature(data, secret):
    import hashlib
    h = hashlib.new(CONF.get("FSA_TOKEN_HASH", "blake2s"))
    siglen = CONF.get("FSA_TOKEN_LENGTH", 32)
    h.update(f"{data}:{secret}".encode())
    return h.digest()[:siglen].hex()


# build a timestamp string
def get_timestamp(ts):
    return "%04d%02d%02d%02d%02d%02d" % ts.timetuple()[:6]


# compute a token for "user" valid for "delay" minutes, signed with "secret"
def compute_token(realm, user, delay, secret):
    limit = get_timestamp(dt.datetime.utcnow() + dt.timedelta(minutes=delay))
    data = f"{realm}:{user}:{limit}"
    sig = compute_signature(data, secret)
    return f"{data}:{sig}"


# create a new token for user depending on the configuration
def create_token(user):
    delay = CONF.get("FSA_TOKEN_DELAY", 60)
    return compute_token(REALM, user, delay, SECRET)


# tell whether token is ok: return validated user or None
# token form: "realm:calvin:20380119031407:<signature>"
def get_token_auth(token):
    realm, user, limit, sig = token.split(':', 3)
    # check realm
    if realm != REALM:
        log.info(f"LOGIN (token): unexpected realm {realm}")
        raise AuthException(f"unexpected realm: {realm}", 401)
    # check signature
    ref = compute_signature(f"{realm}:{user}:{limit}",
                            CONF["FSA_TOKEN_SECRET"])
    if ref != sig:
        log.info("LOGIN (token): invalid signature")
        raise AuthException("invalid auth token signature", 401)
    # check limit
    now = get_timestamp(dt.datetime.utcnow())
    if now > limit:
        log.info("LOGIN (token): token {token} has expired")
        raise AuthException("expired auth token", 401)
    # all is well
    log.info(f"LOGIN (token): {user}")
    return user


# return authenticated user or throw exception
def get_user():
    # default is to rely on the http server provided authentication
    auth_type = CONF.get("FSA_TYPE", "httpd")

    if auth_type == "httpd":

        log.info(f"LOGIN (httpd): {request.remote_user}")
        return request.remote_user

    elif auth_type in ("fake", "param", "basic", "token"):

        # whether to attempt token auth
        has_token = "FSA_TOKEN_SECRET" in CONF
        token_name = CONF.get("FSA_TOKEN_NAME", "auth")

        # first look for the token
        if has_token:
            params = request.values if request.json is None else request.json
            token = params.get(token_name, None)
            if token is not None:
                user = get_token_auth(token)
                if user is not None:
                    return user

        # else try actual auth schemes
        if auth_type == "param":
            return get_param_auth()
        elif auth_type == "basic":
            return get_basic_auth()
        elif auth_type == "fake":
            return get_fake_auth()
        else:
            raise AuthException("auth token is required", 401)

    else:

        raise AuthException(f"unexpected FSA_TYPE: {auth_type}", 500)
