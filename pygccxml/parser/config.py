# Copyright 2014-2015 Insight Software Consortium.
# Copyright 2004-2008 Roman Yakovenko.
# Distributed under the Boost Software License, Version 1.0.
# See http://www.boost.org/LICENSE_1_0.txt

"""
Defines C++ parser configuration classes.

"""

import os
import copy
import platform
import subprocess
from .. import utils


class parser_configuration_t(object):

    """
    C++ parser configuration holder

    This class serves as a base class for the parameters that can be used
    to customize the call to a C++ parser.

    This class also allows users to work with relative files paths. In this
    case files are searched in the following order:

       1. current directory
       2. working directory
       3. additional include paths specified by the user

    """

    def __init__(
            self,
            working_directory='.',
            include_paths=None,
            define_symbols=None,
            undefine_symbols=None,
            cflags="",
            compiler=None,
            caster="gccxml",
            keepxml=False,
            compiler_path=None):

        object.__init__(self)
        self.__working_directory = working_directory

        if not include_paths:
            include_paths = []
        self.__include_paths = include_paths

        if not define_symbols:
            define_symbols = []
        self.__define_symbols = define_symbols

        if not undefine_symbols:
            undefine_symbols = []
        self.__undefine_symbols = undefine_symbols

        self.__cflags = cflags

        self.__compiler = compiler

        self.__caster = caster

        self.__keepxml = keepxml

        if caster == 'castxml' and compiler_path is None:
            # Try to guess a path for the compiler
            # Only needed with castxml on Mac or Linux
            if platform.system() != 'Windows':
                # On windows there is no need for the compiler path
                p = subprocess.Popen(
                    ['which', 'clang'], stdout=subprocess.PIPE)
                self.compiler_path = p.stdout.read().decode("utf-8").rstrip()
                # No clang found; use gcc
                if self.compiler_path == '':
                    self.compiler_path = '/usr/bin/c++'
        else:
            self.compiler_path = compiler_path

    def clone(self):
        raise NotImplementedError(self.__class__.__name__)

    @property
    def working_directory(self):
        return self.__working_directory

    @working_directory.setter
    def working_directory(self, working_dir):
        self.__working_directory = working_dir

    @property
    def include_paths(self):
        """list of include paths to look for header files"""
        return self.__include_paths

    @property
    def define_symbols(self):
        """list of "define" directives """
        return self.__define_symbols

    @property
    def undefine_symbols(self):
        """list of "undefine" directives """
        return self.__undefine_symbols

    @property
    def compiler(self):
        """get compiler name to simulate"""
        return self.__compiler

    @compiler.setter
    def compiler(self, compiler):
        """set compiler name to simulate"""
        self.__compiler = compiler

    @property
    def caster(self):
        """get caster (gccxml or castxml)"""
        return self.__caster

    @caster.setter
    def caster(self, caster):
        """set caster (gccxml or castxml)"""
        self.__caster = caster

    @property
    def keepxml(self):
        """Are xml files kept after errors."""
        return self.__keepxml

    @keepxml.setter
    def keepxml(self, keepxml):
        """Set if xml files kept after errors."""
        self.__keepxml = keepxml

    @property
    def compiler_path(self):
        """Get the path for the compiler."""
        return self.__compiler_path

    @compiler_path.setter
    def compiler_path(self, compiler_path):
        """Set the path for the compiler."""
        self.__compiler_path = compiler_path

    @property
    def cflags(self):
        "additional flags to pass to compiler"
        return self.__cflags

    @cflags.setter
    def cflags(self, val):
        self.__cflags = val

    def append_cflags(self, val):
        self.__cflags = self.__cflags + ' ' + val

    def __ensure_dir_exists(self, dir_path, meaning):
        if os.path.isdir(dir_path):
            return
        if os.path.exists(self.working_directory):
            raise RuntimeError(
                '%s("%s") does not exist!' % (meaning, dir_path))
        else:
            raise RuntimeError(
                '%s("%s") should be "directory", not a file.' %
                (meaning, dir_path))

    def raise_on_wrong_settings(self):
        """validates the configuration settings and raises RuntimeError on
        error"""
        self.__ensure_dir_exists(self.working_directory, 'working directory')
        for idir in self.include_paths:
            self.__ensure_dir_exists(idir, 'include directory')


class gccxml_configuration_t(parser_configuration_t):

    """Configuration object to collect parameters for invoking gccxml.

    This class serves as a container for the parameters that can be used
    to customize the call to gccxml.
    """

    def __init__(
            self,
            gccxml_path='',
            working_directory='.',
            include_paths=None,
            define_symbols=None,
            undefine_symbols=None,
            start_with_declarations=None,
            ignore_gccxml_output=False,
            cflags="",
            compiler=None,
            caster="gccxml",
            keepxml=False,
            compiler_path=None):

        parser_configuration_t.__init__(
            self,
            working_directory=working_directory,
            include_paths=include_paths,
            define_symbols=define_symbols,
            undefine_symbols=undefine_symbols,
            cflags=cflags,
            compiler=compiler,
            caster=caster,
            keepxml=keepxml,
            compiler_path=compiler_path)

        self.__gccxml_path = gccxml_path

        if not start_with_declarations:
            start_with_declarations = []
        self.__start_with_declarations = start_with_declarations

        self.__ignore_gccxml_output = ignore_gccxml_output

    def clone(self):
        return copy.deepcopy(self)

    @property
    def gccxml_path(self):
        "gccxml binary location"
        return self.__gccxml_path

    @gccxml_path.setter
    def gccxml_path(self, new_path):
        self.__gccxml_path = new_path

    @property
    def start_with_declarations(self):
        """list of declarations gccxml should start with, when it dumps
        declaration tree"""
        return self.__start_with_declarations

    @property
    def ignore_gccxml_output(self):
        """set this property to True, if you want pygccxml to ignore any
            error warning that comes from gccxml"""
        return self.__ignore_gccxml_output

    @ignore_gccxml_output.setter
    def ignore_gccxml_output(self, val=True):
        self.__ignore_gccxml_output = val

    def raise_on_wrong_settings(self):
        super(gccxml_configuration_t, self).raise_on_wrong_settings()
        if os.path.isfile(self.gccxml_path):
            return
        if os.name == 'nt':
            gccxml_name = 'gccxml' + '.exe'
            environment_var_delimiter = ';'
        elif os.name == 'posix':
            gccxml_name = 'gccxml'
            environment_var_delimiter = ':'
        else:
            raise RuntimeError('unable to find out location of gccxml')
        may_be_gccxml = os.path.join(self.gccxml_path, gccxml_name)
        if os.path.isfile(may_be_gccxml):
            self.gccxml_path = may_be_gccxml
        else:
            for path in os.environ['PATH'].split(environment_var_delimiter):
                gccxml_path = os.path.join(path, gccxml_name)
                if os.path.isfile(gccxml_path):
                    self.gccxml_path = gccxml_path
                    break
            else:
                msg = (
                    'gccxml_path("%s") should exists or to be a valid ' +
                    'file name.') % self.gccxml_path
                raise RuntimeError(msg)

gccxml_configuration_example = \
    """
[gccxml]
#path to gccxml executable file - optional, if not provided, os.environ['PATH']
#variable is used to find it
gccxml_path=
#gccxml working directory - optional, could be set to your source code
directory
working_directory=
#additional include directories, separated by ';'
include_paths=
#gccxml has a nice algorithms, which selects what C++ compiler to emulate.
#You can explicitly set what compiler it should emulate.
#Valid options are: g++, msvc6, msvc7, msvc71, msvc8, cl.
compiler=
# gccxml or castxml
caster=
# Do we keep xml files or not after errors
keepxml=
# Set the path to the compiler
compiler_path=
"""


def load_gccxml_configuration(configuration, **defaults):
    """
    loads GCC-XML configuration from an `.ini` file or any other file class
    :class:`ConfigParser.SafeConfigParser` is able to parse.

    :param configuration: configuration could be
                          string(configuration file path) or instance
                          of :class:`ConfigParser.SafeConfigParser` class

    :rtype: :class:`.gccxml_configuration_t`

    Configuration file skeleton::

       [gccxml]
       #path to gccxml executable file - optional, if not provided,
       os.environ['PATH']
       #variable is used to find it
       gccxml_path=
       #gccxml working directory - optional, could be set to your source
       code directory
       working_directory=
       #additional include directories, separated by ';'
       include_paths=
       #gccxml has a nice algorithms, which selects what C++ compiler
       to emulate.
       #You can explicitly set what compiler it should emulate.
       #Valid options are: g++, msvc6, msvc7, msvc71, msvc8, cl.
       compiler=
       # gccxml or castxml
       caster=
       # Do we keep xml files or not after errors
       keepxml=
       # Set the path to the compiler
       compiler_path=

    """

    parser = configuration
    if utils.is_str(configuration):
        try:
            from configparser import SafeConfigParser
        except ImportError:
            from ConfigParser import SafeConfigParser
        parser = SafeConfigParser()
        parser.read(configuration)
    gccxml_cfg = gccxml_configuration_t()

    values = defaults
    if not values:
        values = {}

    if parser.has_section('gccxml'):
        for name, value in parser.items('gccxml'):
            if value.strip():
                values[name] = value

    for name, value in values.items():
        if isinstance(value, str):
            value = value.strip()
        if name == 'gccxml_path':
            gccxml_cfg.gccxml_path = value
        elif name == 'working_directory':
            gccxml_cfg.working_directory = value
        elif name == 'include_paths':
            for p in value.split(';'):
                p = p.strip()
                if p:
                    gccxml_cfg.include_paths.append(p)
        elif name == 'compiler':
            gccxml_cfg.compiler = value
        elif name == 'caster':
            gccxml_cfg.caster = value
        elif name == 'keepxml':
            gccxml_cfg.keepxml = value
        elif name == 'compiler_path':
            gccxml_cfg.compiler_path = value
        else:
            print('\n%s entry was ignored' % name)
    return gccxml_cfg


if __name__ == '__main__':
    print(load_gccxml_configuration('gccxml.cfg').__dict__)
