#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright (c) 2010-2011 OpenStack, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
TOKEN-BASED AUTH MIDDLEWARE

This WSGI component:

* Verifies that incoming client requests have valid tokens by validating
  tokens with the auth service.
* Rejects unauthenticated requests UNLESS it is in 'delay_auth_decision'
  mode, which means the final decision is delegated to the downstream WSGI
  component (usually the OpenStack service)
* Collects and forwards identity information based on a valid token
  such as user name, tenant, etc

Refer to: http://wiki.openstack.org/openstack-authn

HEADERS
-------

* Headers starting with HTTP\_ is a standard http header
* Headers starting with HTTP_X is an extended http header

Coming in from initial call from client or customer
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

HTTP_X_AUTH_TOKEN
    The client token being passed in.

HTTP_X_STORAGE_TOKEN
    The client token being passed in (legacy Rackspace use) to support
    cloud files

Used for communication between components
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

www-authenticate
    only used if this component is being used remotely

HTTP_AUTHORIZATION
    basic auth password used to validate the connection

What we add to the request for use by the OpenStack service
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

HTTP_X_AUTHORIZATION
    The client identity being passed in

HTTP_X_IDENTITY_STATUS
    'Confirmed' or 'Invalid'
    The underlying service will only see a value of 'Invalid' if the Middleware
    is configured to run in 'delay_auth_decision' mode

HTTP_X_TENANT
    *Deprecated* in favor of HTTP_X_TENANT_ID and HTTP_X_TENANT_NAME
    Keystone-assigned unique identifier, deprecated

HTTP_X_TENANT_ID
    Identity service managed unique identifier, string

HTTP_X_TENANT_NAME
    Unique tenant identifier, string

HTTP_X_USER
    *Deprecated* in favor of HTTP_X_USER_ID and HTTP_X_USER_NAME
    Unique user name, string

HTTP_X_USER_ID
    Identity-service managed unique identifier, string

HTTP_X_USER_NAME
    Unique user identifier, string

HTTP_X_ROLE
    *Deprecated* in favor of HTTP_X_ROLES
    This is being renamed, and the new header contains the same data.

HTTP_X_ROLES
    Comma delimited list of case-sensitive Roles

"""

import eventlet
from eventlet import wsgi
import json
import os
from paste.deploy import loadapp
from urlparse import urlparse
from webob.exc import HTTPUnauthorized
from webob.exc import Request, Response
import keystone.tools.tracer  # @UnusedImport # module runs on import

from keystone.common.bufferedhttp import http_connect_raw as http_connect


PROTOCOL_NAME = "Token Authentication"


class ValidationFailed(Exception):
    pass


class AuthProtocol(object):
    """Auth Middleware that handles authenticating client calls"""

    def _init_protocol_common(self, app, conf):
        """ Common initialization code"""
        print "Starting the %s component" % PROTOCOL_NAME

        self.conf = conf
        self.app = app
        #if app is set, then we are in a WSGI pipeline and requests get passed
        # on to app. If it is not set, this component should forward requests

        # where to find the OpenStack service (if not in local WSGI chain)
        # these settings are only used if this component is acting as a proxy
        # and the OpenSTack service is running remotely
        self.service_protocol = conf.get('service_protocol', 'https')
        self.service_host = conf.get('service_host')
        service_port = conf.get('service_port')
        if service_port:
            self.service_port = int(service_port)
        self.service_url = '%s://%s:%s' % (self.service_protocol,
                                           self.service_host,
                                           self.service_port)
        # used to verify this component with the OpenStack service or PAPIAuth
        self.service_pass = conf.get('service_pass')

        # delay_auth_decision means we still allow unauthenticated requests
        # through and we let the downstream service make the final decision
        self.delay_auth_decision = int(conf.get('delay_auth_decision', 0))

    def _init_protocol(self, conf):
        """ Protocol specific initialization """

        # where to find the auth service (we use this to validate tokens)
        self.auth_host = conf.get('auth_host')
        self.auth_port = int(conf.get('auth_port'))
        self.auth_protocol = conf.get('auth_protocol', 'https')

        # where to tell clients to find the auth service (default to url
        # constructed based on endpoint we have for the service to use)
        self.auth_location = conf.get('auth_uri',
                                        "%s://%s:%s" % (self.auth_protocol,
                                        self.auth_host,
                                        self.auth_port))

        # Credentials used to verify this component with the Auth service since
        # validating tokens is a privileged call
        self.admin_token = conf.get('admin_token')
        # Certificate file and key file used to authenticate with Keystone
        # server
        self.cert_file = conf.get('certfile', None)
        self.key_file = conf.get('keyfile', None)

    def __init__(self, app, conf):
        """ Common initialization code """
        #TODO(ziad): maybe we refactor this into a superclass
        # Defining instance variables here for improving pylint score
        # NOTE(salvatore-orlando): the following vars are assigned values
        # either in init_protocol or init_protocol_common. We should not
        # worry about them being initialized to None
        self.admin_password = None
        self.admin_token = None
        self.admin_user = None
        self.auth_api_version = None
        self.auth_host = None
        self.auth_location = None
        self.auth_port = None
        self.auth_protocol = None
        self.service_host = None
        self.service_port = None
        self.service_protocol = None
        self.service_url = None
        self._init_protocol_common(app, conf)  # Applies to all protocols
        self._init_protocol(conf)  # Specific to this protocol

    def __call__(self, env, start_response):
        """ Handle incoming request. Authenticate. And send downstream. """

        #Prep headers to forward request to local or remote downstream service
        proxy_headers = env.copy()
        for header in proxy_headers.iterkeys():
            if header[0:5] == 'HTTP_':
                proxy_headers[header[5:]] = proxy_headers[header]
                del proxy_headers[header]

        #Look for authentication claims
        claims = self._get_claims(env)
        if not claims:
            #No claim(s) provided
            if self.delay_auth_decision:
                #Configured to allow downstream service to make final decision.
                #So mark status as Invalid and forward the request downstream
                self._decorate_request("X_IDENTITY_STATUS",
                    "Invalid", env, proxy_headers)
            else:
                #Respond to client as appropriate for this auth protocol
                return self._reject_request(env, start_response)
        else:
            # this request is presenting claims. Let's validate them
            try:
                claims = self._verify_claims(claims)
            except ValidationFailed:
                # Keystone rejected claim
                if self.delay_auth_decision:
                    # Downstream service will receive call still and decide
                    self._decorate_request("X_IDENTITY_STATUS",
                        "Invalid", env, proxy_headers)
                else:
                    #Respond to client as appropriate for this auth protocol
                    return self._reject_claims(env, start_response)
            else:
                self._decorate_request("X_IDENTITY_STATUS",
                    "Confirmed", env, proxy_headers)

                # Store authentication data
                if claims:
                    self._decorate_request('X_AUTHORIZATION', "Proxy %s" %
                        claims['user'], env, proxy_headers)

                    self._decorate_request('X_TENANT_ID',
                        claims['tenant']['id'], env, proxy_headers)
                    self._decorate_request('X_TENANT_NAME',
                        claims['tenant']['name'], env, proxy_headers)

                    self._decorate_request('X_USER_ID',
                        claims['user']['id'], env, proxy_headers)
                    self._decorate_request('X_USER_NAME',
                        claims['user']['name'], env, proxy_headers)

                    roles = ','.join(claims['roles'])
                    self._decorate_request('X_ROLES',
                        roles, env, proxy_headers)

                    # Deprecated in favor of X_TENANT_ID and _NAME
                    self._decorate_request('X_TENANT',
                        claims['tenant']['id'], env, proxy_headers)

                    # Deprecated in favor of X_USER_ID and _NAME
                    self._decorate_request('X_USER',
                        claims['user']['id'], env, proxy_headers)

                    # Deprecated in favor of X_ROLES
                    self._decorate_request('X_ROLE',
                        roles, env, proxy_headers)

                    if 'capabilities' in claims \
                            and len(claims['capabilities']) > 0:
                            capabilities = claims['capabilities']
                            self._decorate_request(
                                'X_CAPABILITIES',
                                str(",".join(capabilities)),
                                env, proxy_headers)

                    # NOTE(todd): unused
                    self.expanded = True

        #Send request downstream
        return self._forward_request(env, start_response, proxy_headers)

    def _get_claims(self, env):
        """Get claims from request"""
        claims = env.get('HTTP_X_AUTH_TOKEN', env.get('HTTP_X_STORAGE_TOKEN'))
        return claims

    def _reject_request(self, env, start_response):
        """Redirect client to auth server"""
        return HTTPUnauthorized("Authentication required",
                    [("WWW-Authenticate",
                      "Keystone uri='%s'" % self.auth_location)])(env,
                                                        start_response)

    def _reject_claims(self, env, start_response):
        """Client sent bad claims"""
        return HTTPUnauthorized()(env,
            start_response)

    def _verify_claims(self, claims):
        """Verify claims and extract identity information, if applicable."""

        # Step 1: We need to auth with the keystone service, so get an
        # admin token
        #TODO(ziad): Need to properly implement this, where to store creds
        # for now using token from ini
        #auth = self.get_admin_auth_token("admin", "secrete", "1")
        #admin_token = json.loads(auth)["auth"]["token"]["id"]

        # Step 2: validate the user's token with the auth service
        # since this is a priviledged op,m we need to auth ourselves
        # by using an admin token
        headers = {"Content-type": "application/json",
                    "Accept": "application/json",
                    "X-Auth-Token": self.admin_token}
                    ##TODO(ziad):we need to figure out how to auth to keystone
                    #since validate_token is a priviledged call
                    #Khaled's version uses creds to get a token
                    # "X-Auth-Token": admin_token}
                    # we're using a test token from the ini file for now
        conn = http_connect(self.auth_host, self.auth_port, 'GET',
                            '/v2.0/tokens/%s' % claims, headers=headers,
                            ssl=(self.auth_protocol == 'https'),
                            key_file=self.key_file, cert_file=self.cert_file)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()

        if not str(resp.status).startswith('20'):
            # Keystone rejected claim
            raise ValidationFailed()

        token_info = json.loads(data)

        roles = [role['name'] for role in token_info[
            "access"]["user"]["roles"]]

        # in diablo, there were two ways to get tenant data
        tenant = token_info['access']['token'].get('tenant')
        if tenant:
            # post diablo
            tenant_id = tenant['id']
            tenant_name = tenant['name']
        else:
            # diablo only
            tenant_id = token_info['access']['user'].get('tenantId')
            tenant_name = token_info['access']['user'].get('tenantName')

        verified_claims = {
            'user': {
                'id': token_info['access']['user']['id'],
                'name': token_info['access']['user']['name'],
            },
            'tenant': {
                'id': tenant_id,
                'name': tenant_name
            },
            'roles': roles}

        # Capabilities
        headers = {"Content-type": "application/json",
                    "Accept": "application/json",
                    "X-Auth-Token": self.admin_token}
                    ##TODO(ziad):we need to figure out how to auth to keystone
                    #since validate_token is a priviledged call
                    #Khaled's version uses creds to get a token
                    # "X-Auth-Token": admin_token}
                    # we're using a test token from the ini file for now
        conn = http_connect(self.auth_host, self.auth_port, 'GET',
                            '/v2.0/tokens/%s/endpoints' % claims,
                            headers=headers,
                            ssl=(self.auth_protocol == 'https'),
                            key_file=self.key_file, cert_file=self.cert_file)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()

        try:
            capabilities = token_info['access']['token']['capabilities']
            verified_claims['capabilities'] = capabilities
        except:
            pass

        try:
            catalog_info = json.loads(data)
            for endpoint in catalog_info['endpoints']:
                if endpoint['type'] == "compute":
                    if 'RAX-RBAC-capabilities' in endpoint:
                        verified_claims['capabilities'] = \
                            endpoint['RAX-RBAC-capabilities']
                        break
        except:
            pass

        return verified_claims

    def _decorate_request(self, index, value, env, proxy_headers):
        """Add headers to request"""
        proxy_headers[index] = value
        env["HTTP_%s" % index] = value

    def _forward_request(self, env, start_response, proxy_headers):
        """Token/Auth processed & claims added to headers"""
        self._decorate_request('AUTHORIZATION',
            "Basic %s" % self.service_pass, env, proxy_headers)
        #now decide how to pass on the call
        if self.app:
            # Pass to downstream WSGI component
            return self.app(env, start_response)
            #.custom_start_response)
        else:
            # We are forwarding to a remote service (no downstream WSGI app)
            req = Request(proxy_headers)
            parsed = urlparse(req.url)

            conn = http_connect(self.service_host,
                                self.service_port,
                                req.method,
                                parsed.path,
                                proxy_headers,
                                ssl=(self.service_protocol == 'https'))
            resp = conn.getresponse()
            data = resp.read()

            #TODO(ziad): use a more sophisticated proxy
            # we are rewriting the headers now

            if resp.status == 401 or resp.status == 305:
                # Add our own headers to the list
                headers = [("WWW_AUTHENTICATE",
                   "Keystone uri='%s'" % self.auth_location)]
                return Response(status=resp.status, body=data,
                            headerlist=headers)(env,
                                                start_response)
            else:
                return Response(status=resp.status, body=data)(env,
                                                start_response)


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def auth_filter(app):
        return AuthProtocol(app, conf)
    return auth_filter


def app_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)
    return AuthProtocol(None, conf)

if __name__ == "__main__":
    app = loadapp("config:" + \
        os.path.join(os.path.abspath(os.path.dirname(__file__)),
                     os.pardir,
                     os.pardir,
                    "examples/paste/auth_token.ini"),
                    global_conf={"log_name": "auth_token.log"})
    wsgi.server(eventlet.listen(('', 8090)), app)
