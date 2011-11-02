import ldap
import logging

from .tenant import TenantAPI
from .user import UserAPI
from .role import RoleAPI

LOG = logging.getLogger('keystone.backends.activedirectory.api')


def py2ldap(val):
    if isinstance(val, str):
        return val
    elif isinstance(val, bool):
        return 'TRUE' if val else 'FALSE'
    else:
        return str(val)

LDAP_VALUES = {
    'TRUE': True,
    'FALSE': False,
}


def ldap2py(val):
    try:
        return LDAP_VALUES[val]
    except KeyError:
        pass
    try:
        return int(val)
    except ValueError:
        pass
    return val


def safe_iter(attrs):
    if attrs is None:
        return
    elif isinstance(attrs, list):
        for e in attrs:
            yield e
    else:
        yield attrs


class LDAPWrapper(object):
    def __init__(self, API):
        self.conn = API.get_connection()

    def simple_bind_s(self, user, password):
        LOG.debug("LDAP bind: dn=%s", user)
        return self.conn.simple_bind_s(user, password)

    def add_s(self, dn, attrs):
        ldap_attrs = [(typ, map(py2ldap, safe_iter(values)))
                      for typ, values in attrs]
        if LOG.isEnabledFor(logging.DEBUG):
            sane_attrs = [(typ, values if typ != 'userPassword' else ['****'])
                          for typ, values in ldap_attrs]
            LOG.debug("LDAP add: dn=%s, attrs=%s", dn, sane_attrs)
        return self.conn.add_s(dn, ldap_attrs)

    def search_s(self, dn, scope, query):
        if LOG.isEnabledFor(logging.DEBUG):
            LOG.debug("LDAP search: dn=%s, scope=%s, query=%s", dn,
                        fakeldap.scope_names[scope], query)
        res = self.conn.search_s(dn, scope, query)
        return [(dn, dict([(typ, map(ldap2py, values))
                           for typ, values in attrs.iteritems()]))
                for dn, attrs in res]

    def modify_s(self, dn, modlist):
        ldap_modlist = [(op, typ, None if values is None else
                         map(py2ldap, safe_iter(values)))
                        for op, typ, values in modlist]
        if LOG.isEnabledFor(logging.DEBUG):
            sane_modlist = [(op, typ, values if typ != 'userPassword'
                            else ['****']) for op, typ, values in ldap_modlist]
            LOG.debug("LDAP modify: dn=%s, modlist=%s", dn, sane_modlist)
        return self.conn.modify_s(dn, ldap_modlist)

    def delete_s(self, dn):
        LOG.debug("LDAP delete: dn=%s", dn)
        return self.conn.delete_s(dn)


class API(object):
    apis = ['tenant', 'user', 'role']

    def __init__(self, options):
        self.server = options['server']
        self.use_ssl = options['use_ssl']
        self.cacertfile = options['cacertfile']
        self.use_port = options['port']
        self.user = options['user']
        self.password = options['password']
        self.root = options['root']
        self.role_map = options['role_map']

        self.tenant = TenantAPI(self, options)
        self.user = UserAPI(self, options)
        self.role = RoleAPI(self, options)

    def get_connection(self, user=None, password=None):
        ldap.set_option(ldap.OPT_REFERRALS, 0)
        # Uncomment to debug LDAP: ldap.set_option(ldap.OPT_DEBUG_LEVEL, 255)

        if self.use_ssl:
            assert(ldap.TLS_AVAIL)
            ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
            # No need to change ldap.conf file if we set these here
            if self.cacertfile:
                ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, self.cacertfile)
            if self.port:
                conn = ldap.initialize(
                    'ldaps://%s:%s' % (self.server, self.port))
            else:
                conn = ldap.initialize('ldaps://%s' % self.server)
        else:
            conn = ldap.initialize('ldap://%s' % self.server)

        ldap.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
        self.LDAP.simple_bind_s(self.login, self.password)
        LOG.debug("Logged in as: %s", self.LDAP.whoami_s())

        return conn
