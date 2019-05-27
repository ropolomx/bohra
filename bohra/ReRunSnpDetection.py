import pathlib
import os,getpass
import pandas
import jinja2
import sh
import logging
import filecmp
import datetime
import numpy
import itertools
import subprocess
from Bio import SeqIO, Phylo
from bohra.SnpDetection import RunSnpDetection

class ReRunSnpDetection(RunSnpDetection):


    def __init__(self, args):
        # get date and time
        self.now = datetime.datetime.today().strftime("%d_%m_%y_%H")
        self.day = datetime.datetime.today().strftime("%d_%m_%y")
        # get the working directory
        self.workdir = pathlib.Path(args.workdir)
        # path to pipeline resources
        self.resources = pathlib.Path(args.resources)
        # path to reference => if args.reference is a string, check that it matches existing
        # set force based on args.. this will be set to true if ref is different and/or snippy version 
        self.force = False
        
        # get original data 
        self.get_source()
        # Reference mask and snippy
        
        if self.pipeline != 'a':
            self.check_reference(new = args.reference)
            # check dependencies
            self.check_for_snippy()
            self.mask = self.check_mask(args.mask, original_mask = self.original_mask)
                
        # print(self.mask)
        # min aln 
        
        # set threads
        # user
        self.user = getpass.getuser()
        # gubbins TODO add back in later!!
        if not args.gubbins:
            self.gubbins = numpy.nan
        else:
            self.gubbins = args.gubbins
        
        self.dryrun = args.dryrun
        self.keep = args.keep
    
    def get_source(self):

        '''
        open the source.log file and extract reference, mask, date, snippy_version
        '''
        df = pandas.read_csv('source.log', sep = None, engine = 'python')
        self.pipeline = df.ix[df.index[-1], 'Pipeline']
        if self.pipeline != 'a':
            self.original_reference = df.ix[df.index[-1], 'Reference']
            self.original_mask = df.ix[df.index[-1], 'Mask']
            self.original_snippy_version = df.ix[df.index[-1], 'snippy_version']
        if self.pipeline != 's':
            self.assembler = df.ix[df.index[-1], 'Assembler']
        self.orignal_date = df.ix[df.index[-1], 'Date']
        self.input_file = pathlib.Path(f"{df.ix[df.index[-1], 'input_file']}")
        # print(self.input_file)
        self.job_id = df.ix[df.index[-1], 'JobID']
        self.cpus = df.ix[df.index[-1], 'CPUS']
        self.prefillpath = df.ix[df.index[-1], 'prefillpath']
        self.minaln = df.ix[df.index[-1], 'MinAln']
        
        # return reference, mask, snippy_version, date, input_file, pipeline
        

    def check_reference(self, new):
        # check if refs are the same if not set self.ref to new and change to force, else set ref to original
        if isinstance(new, str) and len(new) > 0 and len(self.original_reference) > 0:
            new_reference = pathlib.Path(f"{new}")
            if f"{new_reference.name}" == self.original_reference:
                self.ref = pathlib.Path(self.original_reference)
            
            else:
                self.ref = self.link_file(path = new_reference)
                self.force = True
                self.log_messages('message', f"You have chosen a different reference from the previous run. Snippy will be forced to run again from the beginning.")
        elif isinstance(new, str) and len(new) == 0 and len(self.original_reference) > 0:
            self.ref = pathlib.Path(self.original_reference)
        else:
            self.log_messages('message', 'There appears to be something wrong with the reference. You will need to run Bohra using the run command.')


    def check_for_snippy(self):
        self.check_setup_files()
        self.current_snippy_version = self.check_deps()
        c = self.current_snippy_version.split('.')
        o = self.original_snippy_version.split('.')
        if c[0] != o[0] and c[1] != o[0]:
            self.force = True


    def update_source_log(self):
        '''
        update source.log if user changes parameters
        '''
        df = pandas.read_csv('source.log', sep = None, engine = 'python')
        data =pandas.DataFrame({'JobID':self.job_id, 'Reference':self.ref,'Mask':self.mask, 'Pipeline': self.pipeline, 'CPUS': self.cpus,'MinAln':self.minaln,'Gubbins': self.gubbins, 'Date':self.day, 'User':self.user,'snippy_version':self.current_snippy_version ,'input_file':f"{self.input_file}",'prefillpath': self.prefillpath,'Assembler':self.assembler},index=[0])

        # new_df = pandas.DataFrame({'JobID':self.job_id, 'Reference':f"{self.ref}",'Mask':self.mask, 
        #                             'MinAln':self.minaln, 
        #                             'Gubbins': self.gubbins, 'Date':self.day, 'User':self.user, 'snippy_version':snippy_version, 'input_file':f"{self.input_file}"},
        #                             index=[0], )
        # print(data)
        df = df.append(data)
        # print(source_log_df)
        df.to_csv('source.log', index=False, sep = '\t')
    
        
    # def run_with_gubbins(self):
    #     '''
    #     Check if user wants to use Gubbins - return Y or N
    #     '''
    #     if self.confirm(f"Would you like to use gubbins to remove recombination?", True):
    #         self.log_messages('info', f"Gubbins will be used to remove recombination today.")
    #         return True
    #     else:
    #         self.log_messages('info', f"No recombination filtering will be used.")
    #         return False
    # TODO change this delete to unlink from pathlib
    def rerun_report(self):
        # os.chdir(self.workdir)
        p1 = pathlib.Path(self.workdir, self.job_id, 'report')
        p2 = pathlib.Path(self.workdir, self.job_id, f"report_{self.orignal_date}")
        if self.keep:
            cmd = f"mv {p1} {p2}"
        else:
            cmd = f"if [ -d {p1} ];then rm -r {p1}; fi"
        subprocess.run(cmd, shell = True)
    
    def remove_core(self):
        corefiles = sorted(pathlib.Path(self.workdir, self.job_id).glob('core*'))
        if corefiles:
            for core in corefiles:
                core.unlink()
        
        

    def run_pipeline(self):

        # update source
        self.update_source_log()
        self.rerun_report()
        self.remove_core()

        isolates = self.set_workflow_input()
        # setup the workflow files Snakefile and config file
        self.setup_workflow(isolates = isolates)
        # run the workflow
        # if self.run_workflow():
        #     self.log_messages('info', f"Report can be found in {self.job_id}")
        #     self.log_messages('info', f"Process specific log files can be found in process directories. Job settings can be found in source.log") 
        #     self.log_messages('info', f"Have a nice day. Come back soon.") 
        #     self.log_messages('info',f"{60 * '='}")
