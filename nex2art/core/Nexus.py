import os
import xml.etree.ElementTree as ET

class Nexus:
    def __init__(self):
        self.path = None
        self.repos = None
        self.repomap = None
        self.dirty = True
        self.ldap = None

    def refresh(self, path):
        repos, repomap = [], {}
        self.path = None
        self.repos = None
        self.repomap = None
        self.dirty = True
        self.ldap = None
        if path == None: return True
        path = os.path.abspath(path)
        config = os.path.join(path, 'conf', 'nexus.xml')
        if not os.path.isfile(config):
            return "Given path is not a valid Nexus instance."
        try:
            xml = ET.parse(config).getroot()
            for repo in xml.find('repositories').findall('repository'):
                repodata = {}
                repodata['id'] = repo.find('id').text
                repodata['desc'] = repo.find('name').text
                repodata['type'], repodata['layout'] = self.getPackType(repo)
                self.getRepoClass(repo, repodata)
                ext = repo.find('externalConfiguration')
                policy = None
                if ext != None: policy = ext.find('repositoryPolicy')
                repodata['release'] = False
                repodata['snapshot'] = False
                if policy != None:
                    repodata['release'] = policy.text in ('RELEASE', 'MIXED')
                    repodata['snapshot'] = policy.text in ('SNAPSHOT', 'MIXED')
                repos.append(repodata)
                repomap[repodata['id']] = repodata
        except: return "Configuration file nexus.xml is not valid."
        repos.sort(key=lambda x: x['class'])
        ldapxml, ldap = os.path.join(path, 'conf', 'ldap.xml'), None
        if os.path.isfile(ldapxml):
            try: ldap = self.getldap(ldapxml)
            except: pass
        self.repos = repos
        self.repomap = repomap
        self.path = path
        self.ldap = ldap
        return True

    def getldap(self, ldapxml):
        tmpdata, ldap = {}, {}
        for prop in ET.parse(ldapxml).getroot().iter():
            tmpdata[prop.tag] = prop.text
        proto, host = tmpdata['protocol'], tmpdata['host']
        port, base = tmpdata['port'], tmpdata['searchBase']
        url = proto + '://' + host
        if (proto, port) not in (('ldap', '389'), ('ldaps', '636')):
            url += ':' + port
        url += '/' + base
        ldap['ldapUrl'] = url
        uoc = tmpdata['userObjectClass']
        uid = tmpdata['userIdAttribute']
        filt = '(&(objectClass=' + uoc + ')(' + uid + '={0})'
        if 'ldapFilter' in tmpdata and len(tmpdata['ldapFilter']) > 0:
            ufilt = tmpdata['ldapFilter']
            if ufilt[0] != '(' or ufilt[-1] != ')':
                ufilt = '(' + ufilt + ')'
            filt += ufilt
        filt += ')'
        ldap['searchFilter'] = filt
        ldap['emailAttribute'] = tmpdata['emailAddressAttribute']
        if 'systemUsername' in tmpdata:
            ldap['managerDn'] = tmpdata['systemUsername']
        if 'userBaseDn' in tmpdata:
            ldap['searchBase'] = tmpdata['userBaseDn']
        if 'userSubtree' in tmpdata:
            ldap['searchSubTree'] = tmpdata['userSubtree']
        else: ldap['searchSubTree'] = 'false'
        lgar = 'ldapGroupsAsRoles'
        if lgar in tmpdata and tmpdata[lgar] == 'true':
            gma = 'groupMemberAttribute'
            umoa = 'userMemberOfAttribute'
            goc = 'group'
            if umoa in tmpdata:
                ldap[gma] = tmpdata[umoa]
                ldap['strategy'] = 'DYNAMIC'
                ldap['groupNameAttribute'] = 'cn'
            else:
                ldap[gma] = tmpdata[gma]
                ldap['strategy'] = 'STATIC'
                ldap['groupNameAttribute'] = tmpdata['groupIdAttribute']
                goc = tmpdata['groupObjectClass']
            ldap['filter'] = '(objectClass=' + goc + ')'
            if 'groupBaseDn' in tmpdata:
                ldap['groupBaseDn'] = tmpdata['groupBaseDn']
            if 'groupSubtree' in tmpdata:
                ldap['subTree'] = tmpdata['groupSubtree']
            else: ldap['subTree'] = 'false'
        return ldap

    def getRepoClass(self, repo, repodata):
        ext = repo.find('externalConfiguration')
        members, master = None, None
        if ext != None:
            members = ext.find('memberRepositories')
            master = ext.find('masterRepositoryId')
        remote = repo.find('remoteStorage')
        local = repo.find('localStorage')
        if local != None:
            localurl = local.find('url')
            if localurl != None:
                lurl = localurl.text
                if lurl[-1] != '/': lurl += '/'
                repodata['localurl'] = lurl
        if members != None:
            repodata['class'] = 'virtual'
            repodata['repos'] = []
            for child in members.findall('memberRepository'):
                repodata['repos'].append(child.text)
        elif remote != None:
            repodata['class'] = 'remote'
            repodata['remote'] = remote.find('url').text
        elif master != None: repodata['class'] = 'shadow'
        else: repodata['class'] = 'local'

    def getPackType(self, repo):
        rtypes = ['maven1', 'maven2', 'npm', 'nuget', 'gems']
        ltypes = ['bower', 'gradle', 'ivy', 'npm', 'nuget', 'sbt', 'vcs']
        hint = repo.find('providerHint').text
        if hint == None: return 'generic', 'simple-default'
        subs = hint[hint.rfind('-'):]
        if subs in ('-shadow', '-hosted', '-proxy', '-group'):
            hint = hint[:hint.rfind('-')]
        if hint == 'm2-m1': hint = 'maven1'
        elif hint == 'm1-m2': hint = 'maven2'
        elif hint == 'rubygems': hint = 'gems'
        if hint not in rtypes: hint = 'generic'
        layout = 'simple'
        if hint in ltypes: layout = hint
        elif hint == 'maven1': hint, layout = 'maven', 'maven-1'
        elif hint == 'maven2': hint, layout = 'maven', 'maven-2'
        return hint, layout + '-default'