# Flask Simple Auth

Simple authentication, authorization and parameter checks
for [Flask](https://flask.palletsprojects.com/), controled from
Flask configuration and decorators.


## Description

Help to manage authentication, authorizations and parameters in
a Flask REST application.

**Authentication** is available through the `get_user` function.
It is performed on demand when the function is called, automatically when
checking for permissions in a per-role authorization model, or possibly
forced for all/most paths.

The module implements inheriting the web-server authentication,
password authentication (HTTP Basic, or HTTP/JSON parameters),
simple time-limited authentication tokens, and
a fake authentication scheme useful for application testing.

It allows to have a login route to generate authentication tokens.
For registration, support functions allow to hash new passwords consistently
with password checks.

**Authorization** can be managed with a simple decorator to declare required
permissions on a route (eg a role name), and relies on a supplied function to
check whether a user has this role.  This approach is enough for basic
authorization management, but would be insufficient for realistic applications
where users can edit their own data but not those of others.

**Parameters** expected in the request can be declared, their presence and type
checked, and they are added automatically as named parameters to route functions,
skipping the burden of checking them in typical REST functions.


## Simple Example

The application code below performs authentication, authorization and
parameter checks triggered by decorators.
There is no clue in the source about what kind of authentication is used,
which is the whole point: authentication schemes are managed elsewhere, not
explicitely in the application code.

```Python
# app is the Flask application…
# user_to_password_fun is a function returning the hashed password for a user.
# user_in_group_fun is a function telling whether a user is in a group.

# initialize module
import FlaskSimpleAuth as fsa
fsa.setConfig(app, user_to_password_fun, user_in_group_fun)

# users belonging to the "patcher" group can patch "whatever/*"
# the function gets 3 arguments: one coming from the path (id)
# and the remaining two coming from request parameters (some, stuff).
@app.route("/whatever/<int:id>", methods=["PATCH"])
@fsa.authorize("patcher")
@fsa.autoparams(required=True)
def patch_whatever(id: int, some: int, stuff: str):
    # ok to do it, with parameters id, some & stuff
    return "", 204
```

Authentication is manage from the application flask configuration
with `FSA_*` (Flask simple authentication) directives:

```Python
FSA_TYPE = 'httpd'     # inherit web-serveur authentication
# OR others such as:
FSA_TYPE = 'basic'     # HTTP Basic auth
FSA_TYPE = 'param'     # HTTP parameter auth
```

Various aspects of the implemented schemes can be configured with other
directives, with reasonable defaults provided so that not much is really
needed beyond choosing the authentication scheme.


## Documentation

### Install

Use `pip install FlaskSimpleAuth` to install the module, or whatever
other installation method you prefer.

### Features

This simple module allows configurable authentication (`FSA_TYPE`):

- `httpd` web-server checked authentication passed in the request.

- `basic` http basic auth with a function hook for getting
  the password hash.

- `param` same with http parameter-provided login/password.

- `password` tries `basic` then `param`.

- `token` auth uses a signed parameter to authenticate a
  user in a realm for some limited time. The token can be
  obtained by actually authenticating with other methods.

- `fake` parameter-based auth for fast and simple testing
  the claimed login is coldly trusted…

I have considered [Flask HTTPAuth](https://github.com/miguelgrinberg/Flask-HTTPAuth)
obviously, which provides many options, but I do not want to force their
per-route-only model and explicit classes but rather rely on mandatory request hooks
and have everything managed from the configuration file to easily switch
between schemes, without impact on the application code.

Note that this is intended for a REST API implementation serving
a remote application. It does not make much sense to "login" and "logout"
to/from a REST API because the point of the API is to serve and collect data
to all who deserve it, i.e. are authorized, unlike a web application
which is served while the client is on the page which maintains a session
and should disappear when disconnected as the web browser page is wiped out.
However, there is still a "login" concept which is only dedicated at
obtaining an auth token, that the application client needs to update from
time to time.

Note that web-oriented flask authentication modules are not really
relevant in the REST API context, where the server does not care about
presenting login forms for instance.

### Initialisation

The module is initialized by calling `setConfig` with three arguments:

 - the Flask application object.
 - a function to retrieve the password hash from the user name.
 - a function which tells whether a user is in a group or role.

```Python
# app is already initialized and configured the Flask application

# return password hash if any, or None
def get_user_password(user):
    return …

# return whether user is in group
def user_in_group(user, group):
    return …

import FlaskSimpleAuth as fsa
fsa.setConfig(app, get_user_password, user_in_group)
```

Then the module can be used to retrieve the authenticated user with `get_user`,
which raises `AuthException` on failures.
Some path may require to skip authentication, for instance registering a new user.

Three directives impact how and when authentication is performed.

- `FSA_TYPE` governs the *how*: `httpd`, `basic`, `param`, `password`, `token`…
as described below.
Default is `httpd`.

- `FSA_ALWAYS` tells whether to perform authentication in a before request
hook. Default is *True*.  On authentication failures *401* are returned.
One in a route function, `get_user` will always return the authenticated
user and cannot fail.

- `FSA_SKIP_PATH` is a list of regular expression patterns which are matched
against the request path for skipping systematic authentication.
Default is empty, i.e. authentication is applied for all paths.

- `FSA_LAZY` tells whether to attempt authentication lazily when checking an
authorization through a `authorize` decorator.
Default is *True*.


### Using Authentication, Authorization and Parameter Check

Then all route functions can take advantage of this information to check for
authorizations with the `authorize` decorator, and for mandatory parameters
with the `parameters` decorator.

```Python
@app.route("/somewhere", methods=["POST"])
@fsa.authorize("posters")
@fsa.parameters("listof", "mandatory", "parameters")
def post_somewhere():
    …
```

Note that more advanced permissions (eg users can edit themselves) will
still require manual permission checks at the beginning of the function.

An opened route for user registration could look like that:

```Python
# with FSA_SKIP_PATH = (r"/register", …)
@app.route("/register", methods=["POST"])
@fsa.autoparams(True)
def post_register(user: str, password: str):
    if user_already_exists_somewhere(user):
        return f"cannot create {user}", 409
    add_new_user_with_hashed_pass(user, fsa.hash_password(password))
    return "", 201
```

For `token` authentication, a token can be created on a path authenticated
by one of the other methods. The code for that would be as simple as:

```Python
# token creation route
@app.route("/login", methods=["GET"])
def get_login():
    return jsonify(fsa.create_token(get_user())), 200
```

The client application will return the token as a parameter for
authenticating later requests, till it expires.

The main configuration directive is `FSA_TYPE` which governs authentication
methods used by the `get_user` function, as described in the following sections:

### `httpd` Authentication

Inherit web server supplied authentication through `request.remote_user`.
This is the default.

There are plenty authentication schemes available in a web server
such as Apache or Nginx, all of which probably more efficiently implemented
than python code, so this should be the preferred option.
However, it could require significant configuration effort compared to
the application-side approach.

### `basic` Authentication

HTTP Basic password authentication, which rely on the `Authorization`
HTTP header in the request.

See also Password Authentication below for how the password is retrieved
and checked.

### `param` Authentication

HTTP parameter or JSON password authentication.
User name and password are passed as request parameters.

The following configuration directives are available:

 - `FSA_PARAM_USER` parameter name for the user name.
   Default is `USER`.
 - `FSA_PARAM_PASS` parameter name for the password.
   Default is `PASS`.

See also Password Authentication below for how the password is retrieved
and checked.

### `password` Authentication

Tries `basic` then `param` authentication.

### `token` Authentication

Only rely on signed tokens for authentication.
A token certifies that a *user* is authenticated in a *realm* up to some
time *limit*.
The token is authenticated by a signature which is the hash of the payload
(*realm*, *user* and *limit*) and a secret hold by the server.
The token syntax is: `<realm>:<user>:<limit>:<signature>`,
for instance: `kiva:calvin:20210221160258:4ee89cd4cc7afe0a86b26bdce6d11126`.
The time limit is an easily parsable UTC timestamp *YYYYMMDDHHmmSS* so that
it can be checked easily by the application client.

The following configuration directives are available:

 - `FSA_TOKEN_REALM` realm of token.
   Default is the simplified lower case application name.
 - `FKA_TOKEN_NAME` name of parameter holding the auth token.
   Default is `auth`.
 - `FSA_TOKEN_SECRET` secret string used for signing tokens.
   Default is a system-generated random string containing 128 bits.
   This default with only work with itself, as it is not shared
   across server instances or processes. Set to `None` to disable tokens.
 - `FSA_TOKEN_DELAY` number of minutes of token validity.
   Default is *60* minutes. 
 - `FSA_TOKEN_GRACE` number of minutes of grace time for token validity.
   Default is *0* minutes.
 - `FSA_TOKEN_HASH` hash algorithm used to sign the token.
   Default is `blake2s`.
 - `FSA_TOKEN_LENGTH` number of hash bytes kept for token signature.
   Default is *16*.

Function `create_token(user)` creates a token for the user.

Note that token authentication is always attempted unless the secret is empty.
Setting `FSA_TYPE` to `token` results in *only* token authentication to be used.

Also note that token authentication is usually much faster than password verification
because password checks are designed to be slow so as to hinder password cracking.
Another benefit of token is that it avoids sending passwords over and over.
The rational option is to use a password scheme to retrieve a token and then to
use it till it expires.

### `fake` Authentication

Trust a parameter for authentication claims.
Only for local tests, obviously.
This is inforced.

The following configuration directive is available:

 - `FSA_FAKE_LOGIN` name of parameter holding the user name.
   Default is `LOGIN`.

### Password Authentication (`param` or `basic`)

For checking passwords the password (salted hash) must be retrieved through
`get_user_password(user)`. 
This function must be provided by the application when the module is initialized.

The following configuration directives are available to configure
`passlib` password checks:

 - `FSA_PASSWORD_SCHEME` password scheme to use for passwords.
   Default is `bcrypt`.
   See [passlib documentation](https://passlib.readthedocs.io/en/stable/lib/passlib.hash.html)
   for available options.
 - `FSA_PASSWORD_OPTIONS` relevant options (for `passlib.CryptContext`).
   Default is `{'bcrypt__default_rounds': 4}`.

Beware that modern password checking is often pretty expensive in order to
thwart password cracking if the hashed passwords are leaked, so that you
do not want to have to use that on every request in real life (eg hundreds
milliseconds for passlib bcrypt 12 rounds).
The above defaults result in manageable password checks of a few milliseconds.
Consider enabling tokens to reduce the authentication load on each request.

Function `hash_password(pass)` computes the password salted digest compatible
with the current configuration.

### `authorize` Decorator

The decorator expects a list of identifiers, which are typically names or
numbers.
When several groups are specified, any will allow the operation to proceed.

```Python
# group ids
ADMIN, WRITE, READ = 1, 2, 3

@app.route("/some/place", methods=["POST"])
@fsa.authorize(ADMIN, WRITE)
def post_some_place():
    …
```

The check will call `user_in_group(user, group)` function to check whether the
authenticated user belongs to any of the authorized groups.

The following configuration directive is available:

 - `FSA_LAZY` allows the `authorize` decorator to perform the authentication
   when needed, which mean that the before request hook can be skipped.
   Default is *True*.

Note that this simplistic model does is not enough for non-trivial applications,
where permissions on objects often depend on the object owner.
For those, careful per-operation authorization will still be needed.

###  `parameters` Decorator

This decorator has two flavors.

With positional string arguments, it expects these parameter names and
generates a *400* if any is missing from the request, and passes them
to function named parameters.
The decorator looks for HTTP or JSON parameters.

```Python
@app.route("/thing/<int:tid>", methods=["PUT"])
@fsa.parameters("name")
def put_thing_tid(tid, name):
    …
```

With named parameters associated to a type, it expects these parameter names
and generate a *400* if any is missing from the request, it converts the
parameter string value to the expected type, resulting in a *400* again if the type
conversion fails, and it passes these to the function as named parameters.

```Python
@app.route("/add", methods=["GET"])
@fsa.parameters(a=float, b=float)
def get_add(a, b):
    return str(a + b), 200
```

The `parameters` decorator is declared place *after* the `authorize` decorator,
so that parameter checks are only attempted if the user actually has permissions.

### `autoparams` Decorator

This decorators translates automatically request parameters (HTTP or JSON)
to function parameters, relying on function type annotations to do that.
The `required` parameter allows to declare whether parameters must be set
(when *True*), or whether they are optional (*False*) in which case *None* values
are passed. Default is that parameters are required.

```Python
@app.route("/thing/<int:tid>", methods=["PATCH"])
@fsa.autoparams(False)
def patch_thing_tid(tid: int, name: str, price: float):
    if name is not None:
        update_name(tid, name)
    …
    return "", 204
```

The `autoparams` decorator should be place after the `authorize` decorator.


## Versions

Sources are available on [GitHub](https://github.com/zx80/flask-simple-auth)
and packaged on [PyPI](https://pypi.org/project/FlaskSimpleAuth/).

### dev

Simplify code.
Add `FSA_ALWAYS` configuration directive and move the authentication before request
hook logic inside the module.
Add `FSA_SKIP_PATH` to skip authentication for some paths.
Update documentation to reflect this simplified model.

### 1.6.0

Add `autoparams` decorator with required or optional parameters.
Add typed parameters to `parameters` decorator.
Make `parameters` pass request parameters as named function parameters.
Simplify `authorize` decorator syntax and implementation.
Advise `authorize` *then* `parameters` or `autoparams` decorator order.
Improved documentation.

### 1.5.0

Flask *internal* tests with a good coverage.
Switch to `setup.cfg` configuration.
Add convenient `parameters` decorator.

### 1.4.0

Add `FSA_LAZY` configuration directive.
Simplify code.
Improve warning on short secrets.
Repackage…

### 1.3.0

Improved documentation.
Reduce default token signature length and default token secret.
Warn on random or short token secrets.

### 1.2.0

Add grace time for auth token validity.
Some code refactoring.

### 1.1.0

Add after request module cleanup.

### 1.0.0

Add `authorize` decorator.
Add `password` authentication scheme.
Improved documentation.

### 0.9.0

Initial release in beta.


## TODO

Features
 - better control which schemes are attempted?
 - add support for JWT?

Implementation
 - should it be an object instead of a flat module?
 - expand tests

How not to forget autorizations?
 - set a `autorization_checked` variable to False before the request
 - reset it to True when autorization is checked
 - check whether it was done and possibly abort after the request

