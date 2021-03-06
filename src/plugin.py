###
# Copyright (c) 2002-2005, Jeremiah Fincher
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

import os
import sys
import imp
import os.path
import linecache
import re

from . import callbacks, conf, log, registry

installDir = os.path.dirname(sys.modules[__name__].__file__)
_pluginsDir = os.path.join(installDir, 'plugins')

class Deprecated(ImportError):
    pass

def loadPluginModule(name, ignoreDeprecation=False):
    """Loads (and returns) the module for the plugin with the given name."""
    files = []
    pluginDirs = conf.supybot.directories.plugins()[:]
    pluginDirs.append(_pluginsDir)
    for dir in pluginDirs:
        try:
            files.extend(os.listdir(dir))
        except EnvironmentError: # OSError, IOError superclass.
            log.warning('Invalid plugin directory: %s; removing.', dir)
            conf.supybot.directories.plugins().remove(dir)
    if name not in files:
        search = lambda x: re.search(r'(?i)^%s$' % (name,), x)
        matched_names = list(filter(search, files))
        if len(matched_names) == 1:
            name = matched_names[0]
        else:
            raise ImportError(name)
    moduleInfo = imp.find_module(name, pluginDirs)
    try:
        module = imp.load_module(name, *moduleInfo)
    except:
        sys.modules.pop(name, None)
        keys = sys.modules.keys()
        for key in keys:
            if key.startswith(name + '.'):
                sys.modules.pop(key)
        raise
    if 'deprecated' in module.__dict__ and module.deprecated:
        if ignoreDeprecation:
            log.warning('Deprecated plugin loaded: %s', name)
        else:
            raise Deprecated(format('Attempted to load deprecated plugin %s',
                                     name))
    if module.__name__ in sys.modules:
        sys.modules[module.__name__] = module
    linecache.checkcache()
    return module

def loadPluginClass(irc, module, register=None):
    """Loads the plugin Class from the given module into the given Irc."""
    try:
        cb = module.Class(irc)
    except TypeError as e:
        s = str(e)
        if '2 given' in s and '__init__' in s:
            raise callbacks.Error('In our switch from CVS to Darcs (after 0.80.1), we ' \
                  'changed the __init__ for callbacks.Privmsg* to also ' \
                  'accept an irc argument.  This plugin (%s) is overriding ' \
                  'its __init__ method and needs to update its prototype ' \
                  'to be \'def __init__(self, irc):\' as well as passing ' \
                  'that irc object on to any calls to the plugin\'s ' \
                  'parent\'s __init__. Another possible cause: the code in ' \
                  'your __init__ raised a TypeError when calling a function ' \
                  'or creating an object, which doesn\'t take 2 arguments.' %\
                  module.__name__)
        else:
            raise
    except AttributeError as e:
        if 'Class' in str(e):
            raise callbacks.Error('This plugin module doesn\'t have a "Class" ' \
                  'attribute to specify which plugin should be ' \
                  'instantiated.  If you didn\'t write this ' \
                  'plugin, but received it with Supybot, file ' \
                  'a bug with us about this error.')
        else:
            raise
    cb.classModule = module
    plugin = cb.name()
    public = True
    if hasattr(cb, 'public'):
        public = cb.public
    conf.registerPlugin(plugin, register, public)
    assert not irc.getCallback(plugin), \
           'There is already a %r plugin registered.' % plugin
    try:
        renames = []#XXX registerRename(plugin)()
        if renames:
            for command in renames:
                v = registerRename(plugin, command)
                newName = v()
                assert newName
                renameCommand(cb, command, newName)
        else:
            conf.supybot.commands.renames.unregister(plugin)
    except registry.NonExistentRegistryEntry as e:
        pass # The plugin isn't there.
    irc.addCallback(cb)
    return cb

# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
