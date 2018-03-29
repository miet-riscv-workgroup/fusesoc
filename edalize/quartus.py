import os.path
import logging

from fusesoc.edatool import EdaTool

logger = logging.getLogger(__name__)

class Quartus(EdaTool):

    tool_options = {'members' : {'family' : 'String',
                                 'device' : 'String'},
                    'lists'   : {'quartus_options' : 'String'}}

    argtypes = ['vlogdefine', 'vlogparam']

    MAKEFILE_TEMPLATE = """#Auto generated by FuseSoC
all: sta

include config.mk

project: $(DESIGN_NAME).tcl qsys
	quartus_sh $(QUARTUS_OPTIONS) -t $(DESIGN_NAME).tcl

map: project
	quartus_map $(QUARTUS_OPTIONS) $(DESIGN_NAME)

fit: map
	quartus_fit $(QUARTUS_OPTIONS) $(DESIGN_NAME)

asm: fit
	quartus_asm $(QUARTUS_OPTIONS) $(DESIGN_NAME)

sta: asm
	quartus_sta $(QUARTUS_OPTIONS) $(DESIGN_NAME)

clean:
	rm -rf *.* db incremental_db
"""

    CONFIG_MK_TEMPLATE = """#Auto generated by FuseSoC

DESIGN_NAME := {design_name}
QUARTUS_OPTIONS := {quartus_options}

qsys:"""

    QSYS_TEMPLATE = """
	ip-generate \
--project-directory={src_dir} \
--output-directory={dst_dir} \
--report-file=bsf:{dst_dir}/{name}.bsf \
--system-info=DEVICE_FAMILY="{family}" \
--system-info=DEVICE={device} \
--component-file={src_dir}/{name}.qsys
	ip-generate \
--project-directory={src_dir} \
--output-directory={dst_dir}/synthesis \
--file-set=QUARTUS_SYNTH \
--report-file=sopcinfo:{dst_dir}/{name}.sopcinfo \
--report-file=html:{dst_dir}/{name}.html \
--report-file=qip:{dst_dir}/{name}.qip \
--report-file=cmp:{dst_dir}/{name}.cmp \
--report-file=svd \
--system-info=DEVICE_FAMILY="{family}" \
--system-info=DEVICE={device} \
--component-file={src_dir}/{name}.qsys \
--language=VERILOG
"""

    def configure_main(self):
        for i in ['family', 'device']:
            if not i in self.tool_options:
                raise RuntimeError("Missing required option '{}'".format(i))

        with open(os.path.join(self.work_root, self.name.replace('.', '_')+'.tcl'), 'w') as tcl_file:
            s = """project_new {} -overwrite
set_global_assignment -name FAMILY "{}"
set_global_assignment -name DEVICE {}
set_global_assignment -name TOP_LEVEL_ENTITY {}
"""

            tcl_file.write(s.format(self.name.replace('.', '_'),
                                    self.tool_options['family'],
                                    self.tool_options['device'],
                                    self.toplevel))

            for key, value in self.vlogparam.items():
                tcl_file.write("set_parameter -name {} {}\n".format(key, self._param_value_str(value)))
            for key, value in self.vlogdefine.items():
                tcl_file.write('set_global_assignment -name VERILOG_MACRO "{}={}"\n'.format(key, self._param_value_str(value)))

            (src_files, incdirs) = self._get_fileset_files()

            qsys_files = []
            for f in src_files:
                if f.file_type in ["verilogSource",
                                   "verilogSource-95",
                                   "verilogSource-2001",
                                   "verilogSource-2005"]:
                    _type = 'VERILOG_FILE'
                elif f.file_type in ["systemVerilogSource",
                                     "systemVerilogSource-3.0",
                                     "systemVerilogSource-3.1",
                                     "systemVerilogSource-3.1a"]:
                    _type = 'SYSTEMVERILOG_FILE'
                elif f.file_type in ['vhdlSource',
                                     'vhdlSource-87',
                                     'vhdlSource-93',
                                     'vhdlSource-2008']:
                    _type = 'VHDL_FILE'
                elif f.file_type in ['QIP']:
                    _type = 'QIP_FILE'
                elif f.file_type in ['QSYS']:
                    #Each qsys file will be run through ip-generate, which will
                    #generate a qip file with the same name as the qsys file
                    #The qip will will be stored in work_root/qsys/name/name.qip
                    #Therefore we replace the qsys_file with the qip file here
                    _src_dir = os.path.dirname(f.name)
                    _name = os.path.basename(f.name).split('.qsys')[0]
                    _dst_dir = os.path.join('qsys', _name)

                    qsys_files.append((_src_dir, _dst_dir, _name))

                    f.name = os.path.join(_dst_dir, _name+'.qip')
                    _type = 'QIP_FILE'
                elif f.file_type in ['SDC']:
                    _type = 'SDC_FILE'
                elif f.file_type in ['tclSource']:
                    tcl_file.write("source {}\n".format(f.name.replace('\\', '/')))
                    _type = None
                elif f.file_type in ['user']:
                    _type = None
                else:
                    _type = None
                    _s = "{} has unknown file type '{}'"
                    logger.warning(_s.format(f.name,
                                             f.file_type))
                if _type:
                    _s = "set_global_assignment -name {} {}\n"
                    tcl_file.write(_s.format(_type,
                                             f.name.replace('\\', '/')))

            for include_dir in incdirs:
                tcl_file.write("set_global_assignment -name SEARCH_PATH " + include_dir.replace('\\', '/') + '\n')

        with open(os.path.join(self.work_root, 'Makefile'), 'w') as makefile:
            makefile.write(self.MAKEFILE_TEMPLATE)

        with open(os.path.join(self.work_root, 'config.mk'), 'w') as config_mk:
            if 'quartus_options' in self.tool_options:
                quartus_options = ' '.join(self.tool_options['quartus_options'])
            else:
                quartus_options = ""
            config_mk.write(self.CONFIG_MK_TEMPLATE.format(
                design_name     = self.name.replace('.', '_'),
                quartus_options = quartus_options))
            for qsys_file in qsys_files:
                config_mk.write(self.QSYS_TEMPLATE.format(
                    src_dir = qsys_file[0],
                    dst_dir = qsys_file[1],
                    name    = qsys_file[2],
                    family  = self.tool_options['family'],
                    device  = self.tool_options['device']))

    def run(self, remaining):
        args = ['--mode=jtag']
        args += remaining
        args += ['-o']
        args += ['p;' + self.name.replace('.', '_') + '.sof']
        self._run_tool('quartus_pgm', args)