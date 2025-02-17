# Copyright 2014-2017 Insight Software Consortium.
# Copyright 2004-2009 Roman Yakovenko.
# Distributed under the Boost Software License, Version 1.0.
# See http://www.boost.org/LICENSE_1_0.txt

import os
import platform
import subprocess

from pygccxml import declarations

from . import linker
from . import config
from . import patcher
from . import declarations_cache
from . import declarations_joiner
from .etree_scanner import ietree_scanner_t as scanner_t

from .. import utils


class source_reader_t(object):
    """
    This class reads C++ source code and returns the declarations tree.

    This class is the only class that works directly with CastXML.

    It has only one responsibility: it calls CastXML with a source file
    specified by the user and creates declarations tree. The implementation of
    this class is split to two classes:

    1. `scanner_t` - this class scans the "XML" file, generated by CastXML
        or CastXML and creates :mod:`pygccxml` declarations and types classes.
        After the XML file has been processed declarations and type class
        instances keeps references to each other using CastXML generated id's.

    2. `linker_t` - this class contains logic for replacing CastXML
        generated ids with references to declarations or type class instances.
    """

    def __init__(self, configuration, cache=None, decl_factory=None):
        """
        :param configuration:
                       Instance of :class:`xml_generator_configuration_t`
                       class, that contains CastXML configuration.

        :param cache: Reference to cache object, that will be updated after a
                      file has been parsed.
        :type cache: Instance of :class:`cache_base_t` class

        :param decl_factory: Declarations factory, if not given default
                             declarations factory( :class:`decl_factory_t` )
                             will be used.

        """

        self.logger = utils.loggers.cxx_parser
        self.__search_directories = []
        self.__config = configuration
        self.__cxx_std = utils.cxx_standard(configuration.cflags)
        self.__search_directories.append(configuration.working_directory)
        self.__search_directories.extend(configuration.include_paths)
        if not cache:
            cache = declarations_cache.dummy_cache_t()
        self.__dcache = cache
        self.__config.raise_on_wrong_settings()
        self.__decl_factory = decl_factory
        if not decl_factory:
            self.__decl_factory = declarations.decl_factory_t()
        self.__xml_generator_from_xml_file = None

    @property
    def xml_generator_from_xml_file(self):
        """
        Configuration object containing information about the xml generator
        read from the xml file.

        Returns:
            utils.xml_generators: configuration object
        """
        return self.__xml_generator_from_xml_file

    def __create_command_line(self, source_file, xml_file):
        """
        Generate the command line used to build xml files.

        """
        return self.__create_command_line_castxml(source_file, xml_file)

    def __create_command_line_common(self):
        assert isinstance(self.__config, config.xml_generator_configuration_t)

        cmd = []

        # Add xml generator executable (between "" for windows)
        cmd.append('"%s"' % os.path.normpath(self.__config.xml_generator_path))

        # Add all passed cflags
        if self.__config.cflags != "":
            cmd.append(" %s " % self.__config.cflags)

        # Add additional includes directories
        dirs = self.__search_directories
        cmd.append(''.join([' -I"%s"' % search_dir for search_dir in dirs]))

        return cmd

    def __create_command_line_castxml(self, source_file, xmlfile):

        cmd = self.__create_command_line_common()

        # Clang option: -c Only run preprocess, compile, and assemble steps
        cmd.append("-c")
        # Clang option: make sure clang knows we want to parse c++
        cmd.append("-x c++")

        # Always require a compiler path at this point
        if self.__config.compiler_path is None:
            raise (RuntimeError(
                "Please pass the compiler_path as argument to " +
                "your xml_generator_configuration_t(), or add it to your " +
                "pygccxml configuration file."))

        # Platform specific options
        if platform.system() == 'Windows':
            compilers = ("mingw", "g++", "gcc")
            compiler_path = self.__config.compiler_path.lower()
            if any(compiler in compiler_path for compiler in compilers):
                # Look at the compiler path. This is a bad way
                # to find out if we are using mingw; but it
                # should probably work in most of the cases
                cmd.append('--castxml-cc-gnu ' + self.__config.compiler_path)
            else:
                # We are using msvc
                cmd.append('--castxml-cc-msvc ' +
                           '"%s"' % self.__config.compiler_path)
                if self.__config.compiler == 'msvc9':
                    cmd.append('"-D_HAS_TR1=0"')
        else:
            # On mac or linux, use gcc or clang (the flag is the same)
            cmd.append('--castxml-cc-gnu ')

            if self.__cxx_std.is_implicit:
                std_flag = ''
            else:
                std_flag = ' ' + self.__cxx_std.stdcxx + ' '

            ccflags = self.__config.ccflags
            if std_flag:
                ccflags += std_flag

            if ccflags:
                all_cc_opts = self.__config.compiler_path + ' ' + ccflags
                cmd.append(
                    '"(" ' + all_cc_opts + ' ")"')
            else:
                cmd.append(self.__config.compiler_path)

        if self.__config.castxml_epic_version is not None:
            if self.__config.castxml_epic_version != 1:
                raise RuntimeError(
                    "The CastXML epic version can only be 1, "
                    "but it was " + str(self.__config.castxml_epic_version))
            # Tell castxml to output xml file with a specific epic version
            cmd.append(
                '--castxml-output=' + str(self.__config.castxml_epic_version))
        else:
            # Tell castxml to output xml files that are backward compatible
            # with the format from gccxml
            cmd.append('--castxml-gccxml')

        # Add symbols
        cmd = self.__add_symbols(cmd)

        # The destination file
        cmd.append('-o %s' % xmlfile)
        # The source file
        cmd.append('%s' % source_file)
        # Where to start the parsing
        if self.__config.start_with_declarations:
            cmd.append(
                '--castxml-start "%s"' %
                ','.join(self.__config.start_with_declarations))
        cmd_line = ' '.join(cmd)
        self.logger.debug('castxml cmd: %s', cmd_line)
        return cmd_line

    def __add_symbols(self, cmd):
        """
        Add all additional defined and undefined symbols.

        """

        if self.__config.define_symbols:
            symbols = self.__config.define_symbols
            cmd.append(''.join(
                [' -D"%s"' % def_symbol for def_symbol in symbols]))

        if self.__config.undefine_symbols:
            un_symbols = self.__config.undefine_symbols
            cmd.append(''.join(
                [' -U"%s"' % undef_symbol for undef_symbol in un_symbols]))

        return cmd

    def create_xml_file(self, source_file, destination=None):
        """
        This method will generate a xml file using an external tool.

        The method will return the file path of the generated xml file.

        :param source_file: path to the source file that should be parsed.
        :type source_file: str

        :param destination: if given, will be used as target file path for
                            the xml generator.
        :type destination: str

        :rtype: path to xml file.

        """

        xml_file = destination
        # If file specified, remove it to start else create new file name
        if xml_file:
            utils.remove_file_no_raise(xml_file, self.__config)
        else:
            xml_file = utils.create_temp_file_name(suffix='.xml')

        ffname = source_file
        if not os.path.isabs(ffname):
            ffname = self.__file_full_name(source_file)
        command_line = self.__create_command_line(ffname, xml_file)

        process = subprocess.Popen(
            args=command_line,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

        try:
            results = []
            while process.poll() is None:
                line = process.stdout.readline()
                if line.strip():
                    results.append(line.rstrip())
            for line in process.stdout.readlines():
                if line.strip():
                    results.append(line.rstrip())
            for line in process.stderr.readlines():
                if line.strip():
                    results.append(line.rstrip())

            exit_status = process.returncode
            msg = os.linesep.join([str(s.decode()) for s in results])
            if self.__config.ignore_gccxml_output:
                if not os.path.isfile(xml_file):
                    raise RuntimeError(
                        "Error occurred while running " +
                        self.__config.xml_generator.upper() +
                        ": %s status:%s" %
                        (msg, exit_status))
            else:
                if msg or exit_status or not \
                        os.path.isfile(xml_file):
                    if not os.path.isfile(xml_file):
                        raise RuntimeError(
                            "Error occurred while running " +
                            self.__config.xml_generator.upper() +
                            " xml file does not exist")
                    else:
                        raise RuntimeError(
                            "Error occurred while running " +
                            self.__config.xml_generator.upper() +
                            ": %s status:%s" % (msg, exit_status))
        except Exception:
            utils.remove_file_no_raise(xml_file, self.__config)
            raise
        finally:
            process.wait()
            process.stdout.close()
        return xml_file

    def create_xml_file_from_string(self, content, destination=None):
        """
        Creates XML file from text.

        :param content: C++ source code
        :type content: str

        :param destination: file name for xml file
        :type destination: str

        :rtype: returns file name of xml file
        """
        header_file = utils.create_temp_file_name(suffix='.h')

        try:
            with open(header_file, "w+") as header:
                header.write(content)
            xml_file = self.create_xml_file(header_file, destination)
        finally:
            utils.remove_file_no_raise(header_file, self.__config)
        return xml_file

    def read_file(self, source_file):
        return self.read_cpp_source_file(source_file)

    def read_cpp_source_file(self, source_file):
        """
        Reads C++ source file and returns declarations tree

        :param source_file: path to C++ source file
        :type source_file: str

        """

        xml_file = ''
        try:
            ffname = self.__file_full_name(source_file)
            self.logger.debug("Reading source file: [%s].", ffname)
            decls = self.__dcache.cached_value(ffname, self.__config)
            if not decls:
                self.logger.debug(
                    "File has not been found in cache, parsing...")
                xml_file = self.create_xml_file(ffname)
                decls, files = self.__parse_xml_file(xml_file)
                self.__dcache.update(
                    ffname, self.__config, decls, files)
            else:
                self.logger.debug((
                    "File has not been changed, reading declarations " +
                    "from cache."))
        except Exception:
            if xml_file:
                utils.remove_file_no_raise(xml_file, self.__config)
            raise
        if xml_file:
            utils.remove_file_no_raise(xml_file, self.__config)

        return decls

    def read_xml_file(self, xml_file):
        """
        Read generated XML file.

        :param xml_file: path to xml file
        :type xml_file: str

        :rtype: declarations tree

        """

        assert self.__config is not None

        ffname = self.__file_full_name(xml_file)
        self.logger.debug("Reading xml file: [%s]", xml_file)
        decls = self.__dcache.cached_value(ffname, self.__config)
        if not decls:
            self.logger.debug("File has not been found in cache, parsing...")
            decls, _ = self.__parse_xml_file(ffname)
            self.__dcache.update(ffname, self.__config, decls, [])
        else:
            self.logger.debug(
                "File has not been changed, reading declarations from cache.")

        return decls

    def read_string(self, content):
        """
        Reads a Python string that contains C++ code, and return
        the declarations tree.

        """

        header_file = utils.create_temp_file_name(suffix='.h')
        with open(header_file, "w+") as f:
            f.write(content)

        try:
            decls = self.read_file(header_file)
        except Exception:
            utils.remove_file_no_raise(header_file, self.__config)
            raise
        utils.remove_file_no_raise(header_file, self.__config)

        return decls

    def __file_full_name(self, file_):
        if os.path.isfile(file_):
            return file_
        for path in self.__search_directories:
            file_path = os.path.join(path, file_)
            if os.path.isfile(file_path):
                return file_path
        raise RuntimeError("pygccxml error: file '%s' does not exist" % file_)

    def __parse_xml_file(self, xml_file):
        scanner_ = scanner_t(xml_file, self.__decl_factory, self.__config)
        scanner_.read()
        self.__xml_generator_from_xml_file = \
            scanner_.xml_generator_from_xml_file
        decls = scanner_.declarations()
        types = scanner_.types()
        files = scanner_.files()
        linker_ = linker.linker_t(
            decls=decls,
            types=types,
            access=scanner_.access(),
            membership=scanner_.members(),
            files=files,
            xml_generator_from_xml_file=self.__xml_generator_from_xml_file)
        for type_ in list(types.values()):
            # I need this copy because internaly linker change types collection
            linker_.instance = type_
            declarations.apply_visitor(linker_, type_)
        for decl in decls.values():
            linker_.instance = decl
            declarations.apply_visitor(linker_, decl)
        declarations_joiner.bind_aliases(iter(decls.values()))

        # Patch the declarations tree
        if self.__xml_generator_from_xml_file.is_castxml:
            patcher.update_unnamed_class(decls.values())
        patcher.fix_calldef_decls(
            scanner_.calldefs(), scanner_.enums(), self.__cxx_std)

        decls = [inst for inst in iter(decls.values()) if self.__check(inst)]
        return decls, list(files.values())

    @staticmethod
    def __check(inst):
        return isinstance(inst, declarations.namespace_t) and not inst.parent
