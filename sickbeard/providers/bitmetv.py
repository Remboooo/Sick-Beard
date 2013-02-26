# Author: Rembrand van Lakwijk <rem@lakwijk.com>
# Strongly based on the TorrentLeech plugin.
# URL: http://code.google.com/p/sickbeard/
#
# This file is based upon tvtorrents.py.
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

import sickbeard
import generic
import urllib2
import urllib
import re
import socket
import cookielib
import base64
from dumper import dump

from sickbeard import helpers, logger, exceptions, tvcache


class BitMeTVProvider(generic.TorrentProvider):
    baseUrl = 'http://www.bitmetv.org'
    loginPostTarget = '/takelogin.php'
    urls = {
            'login': '%s/login.php' % baseUrl,
            'captcha': '%s/visual.php' % baseUrl,
            'loginPost': '%s%s' % (baseUrl, loginPostTarget),
            'passkey': '%s/links.php' % baseUrl,
            }
    
    _urlOpener = None
    _cookieJar = None


    def __init__(self):
        generic.TorrentProvider.__init__(self, "BitMeTV")

        self.supportsBacklog = False
        self.cache = BitMeTVCache(self)
        self.url = 'http://www.bitmetv.org/'

    def isEnabled(self):
        return sickbeard.BITMETV

    def imageName(self):
        return 'bitmetv.png'

    def getURL(self, url, headers=[]):
        append_char = '&' if '?' in url else '?'
        url = '%s%suid=%s&passkey=%s&:COOKIE:uid=%s;pass=%s;' % (url, append_char, sickbeard.BITMETV_UID, sickbeard.BITMETV_PASSKEY, sickbeard.BITMETV_UID, sickbeard.BITMETV_PASS)
        # not sure if this is needed as we also include them in the URL, but I guess better safe than sorry.
        headers.append(('Cookie', 'uid=%s;pass=%s;' % (sickbeard.BITMETV_UID, sickbeard.BITMETV_PASS)))
        return generic.GenericProvider.getURL(self, url, headers=headers)

    def _get_cookieJar(self, fresh=False):
        if fresh or not self._cookieJar:
            self._cookieJar = cookielib.CookieJar()
        return self._cookieJar

    def _get_urlOpener(self, fresh=False):
        if fresh or not self._urlOpener:
            self._urlOpener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self._get_cookieJar(fresh=fresh)))
        return self._urlOpener

    def _get_captcha_base64(self):
        opener = self._get_urlOpener(fresh=True)
        url = ''
        try:
            url = self.urls['login']
            opener.open(url)
            url = self.urls['captcha']
            return base64.encodestring(opener.open(url).read())
        except urllib2.URLError as e:
            logger.log("Error while retrieving BitMeTV captcha (URL '%s'): %s" % (url, e), logger.INFO)
            return None

    def _get_html_part(self, regex, html):
        result = re.search(regex, html, re.IGNORECASE)
        if result:
            return result.group(1)
    
    def _get_authorization(self, username, password, captcha):
        url = ''
        opener = self._get_urlOpener()
        try:
            url = self.urls['loginPost']
            data = {'username': username, 'password': password, 'secimage': captcha}
            response = opener.open(url, urllib.urlencode(data))
            if response.geturl().endswith(self.loginPostTarget):
                raise BitMeLoginError(self._get_html_part('<h2>(.*)</h2>',response.read()) or 'Redirected back to login page for unknown reason (credentials? captcha?)')
            result = {}
            for cookie in self._get_cookieJar():
                if cookie.name == 'uid':
                    result['uid'] = cookie.value
                if cookie.name == 'pass':
                    result['pass'] = cookie.value
            if not 'uid' in result or not 'pass' in result:
                raise BitMeLoginError('No uid or pass in returned cookie')
            url = self.urls['passkey']
            response = opener.open(url)
            passkey = self._get_html_part('passkey=([0-9A-Z]{32})',response.read())
            if not passkey:
                raise BitMeLoginError("Could not find passkey on '%s'" % url)
            result['passkey'] = passkey
            for cookie in self._get_cookieJar():
                cookie.expires = None
            return result
        except urllib2.URLError as e:
            raise BitMeLoginError("Error logging in to BitMeTV (URL '%s')" % url, e)
        except socket.timeout as e:
            raise BitMeLoginError("Timeout while logging in (URL '%s')" % url, e)

class BitMeLoginError(Exception):
    def __init__(self, message, cause=None):
        self.message = message
        self.cause = cause
    
    def __str__(self):
        if self.cause is not None:
            return '%s (cause: %s)' % (self.message, self.cause)
        else:
            return self.message

class BitMeTVCache(tvcache.TVCache):

    def __init__(self, provider):
        tvcache.TVCache.__init__(self, provider)

        # only poll every 15 minutes
        self.minTime = 15

    def _getRSSData(self):

        if not sickbeard.BITMETV_UID or not sickbeard.BITMETV_PASSKEY or not sickbeard.BITMETV_PASS:
            raise exceptions.AuthException("BitMeTV requires a uid, passkey and a pass to work correctly")

        url = 'http://www.bitmetv.org/rss.php?feed=dl'
        logger.log(u"BitMeTV cache update URL: " + url, logger.DEBUG)

        data = self.provider.getURL(url)

        return data

    def _parseItem(self, item):
        description = helpers.get_xml_text(item.getElementsByTagName('description')[0])

        if "Your RSS key is invalid" in description:
            raise exceptions.AuthException("BitMeTV uid, passkey or pass invalid")

        (title, url) = self.provider._get_title_and_url(item)

        description = '%s \n%s' % (title, description)

        if not title or not url:
            logger.log(u"The XML returned from the BitMeTV RSS feed is incomplete, this result is unusable", logger.ERROR)
            return

        logger.log(u"Adding item from RSS to cache: " + title, logger.DEBUG)

        self._addCacheEntry(title, url)



provider = BitMeTVProvider()