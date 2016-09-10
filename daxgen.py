#!/usr/bin/env python
import sys
import string
import os
import shutil
import numpy as np
from datetime import datetime
from ConfigParser import ConfigParser
from Pegasus.DAX3 import ADAG, Job, File, Link
from kegparametersfactory import KegParametersFactory

class RefinementWorkflow(object):
    def __init__(self, outdir, config, is_synthetic_workflow):
        "'outdir' is the directory where the workflow is written, and 'config' is a ConfigParser object"
        self.outdir = outdir
        self.config = config
        self.daxfile = os.path.join(self.outdir, "dax.xml")
        self.replicas = {}

        # Get all the values from the config file
        self.angles = [x.strip() for x in self.getconf("angles").split(",")]
        self.mcvine_inp = self.getconf("mcvine_inp")
        self.sim_yml = self.getconf("sim_yml")
        self.beam_tar = self.getconf("beam_tar")

    def getconf(self, name, section="simulation"):
        return self.config.get(section, name)

    def add_replica(self, name, path):
        "Add a replica entry to the replica catalog for the workflow"
        url = "file://%s" % path
        self.replicas[name] = url

    def generate_replica_catalog(self):
        "Write the replica catalog for this workflow to a file"
        path = os.path.join(self.outdir, "rc.txt")
        f = open(path, "w")
        try:
            for name, url in self.replicas.items():
                f.write('%-30s %-100s pool="local"\n' % (name, url))
        finally:
            f.close()

    def generate_dax(self):
        "Generate a workflow (DAX, config files, and replica catalog)"
        ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        dax = ADAG("refinement-%s" % ts)

        # These are all the global input files for the workflow
        mcvine_inp = File(self.mcvine_inp)
        setupjob = Job("mcvine", node_label="mcvine_setup")
        setupjob.addArguments("workflow", "singlecrystal")
        setupjob.addArguments("--outdir", "outdir")
        setupjob.addArguments("--type", "DGS")
        setupjob.addArguments("--instrument", "ARCS")
        setupjob.addArguments("--sample", self.getconf("mcvine_inp"))
        task_label = "mcvine"
        setupjob.uses(mcvine_inp, link=Link.INPUT)
        beam_dir = "./outdir/beam/run-beam.sh"
        setupjob.uses(beam_dir, link=Link.OUTPUT, transfer=False)
        setupjob.profile("globus", "maxwalltime", self.getconf("setup_maxwalltime"))
        setupjob.profile("globus", "count", self.getconf("setup_cores"))
        dax.addJob(setupjob)

        # This job untars the beam directory and makes it available to the other
        # jobs in the workflow
        beam_tar = File(self.beam_tar)

        untarjob = Job("tar", node_label="untar")

        untarjob.addArguments("-xzvf", beam_tar)
        untarjob.addArguments("-C", "./outdir/beam")

        untarjob.uses(beam_tar, link=Link.INPUT)
        untarjob.uses(beam_dir, link=Link.INPUT)
        beam_dir2 = "./outdir/beam/run-m2s.sh"
        untarjob.uses(beam_dir2, link=Link.OUTPUT, transfer=False)

        untarjob.profile("globus", "maxwalltime", "1")
        untarjob.profile("globus", "count", "1")

        dax.addJob(untarjob)


        for angle in np.arange(float(self.angles[0]),float(self.angles[1]),float(self.angles[2])):
            sim_yml = File(self.sim_yml)
            runjob = Job("sim", node_label="mcvine_run")
            runjob.addArguments("--angle="+str(angle))
            runjob.addArguments("--config=../../"+self.sim_yml)
            task_label = "simulation"
            runjob.uses(beam_dir2, link=Link.INPUT)
            runjob.uses(sim_yml, link=Link.INPUT)
            runjob.uses("./outdir/scattering/work_"+str(angle)+"/sim_"+str(angle)+".nxs", link=Link.OUTPUT, transfer=True)
            runjob.profile("globus", "maxwalltime", self.getconf("mcvine_maxwalltime"))
            runjob.profile("globus", "count", self.getconf("mcvine_cores"))
            dax.addJob(runjob)

        # Write the DAX file
        dax.writeXMLFile(self.daxfile)

    def generate_workflow(self):

        # Generate dax
        self.generate_dax()

        # Generate the replica catalog
        self.generate_replica_catalog()

def main():
    if len(sys.argv) < 3:
        raise Exception("Usage: %s --synthetic CONFIGFILE OUTDIR" % sys.argv[0])

    is_synthetic_workflow = (sys.argv[1] == "--synthetic")

    if is_synthetic_workflow:
        configfile = sys.argv[2]
        outdir = sys.argv[3]
    else:
        configfile = sys.argv[1]
        outdir = sys.argv[2]

    if not os.path.isfile(configfile):
        raise Exception("No such file: %s" % configfile)

    if os.path.isdir(outdir):
        raise Exception("Directory exists: %s" % outdir)

    # Create the output directory
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir)

    # Read the config file
    config = ConfigParser()
    config.read(configfile)

    # Save a copy of the config file
    shutil.copy(configfile, outdir)

    # Generate the workflow in outdir based on the config file
    workflow = RefinementWorkflow(outdir, config, is_synthetic_workflow)
    workflow.generate_workflow()


if __name__ == '__main__':
    main()

