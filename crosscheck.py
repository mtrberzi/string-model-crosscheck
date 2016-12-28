#!/usr/bin/env python3

import sys
from antlr4 import *
from SmtLib25Lexer import SmtLib25Lexer
from SmtLib25Parser import SmtLib25Parser
from SmtLib25Visitor import SmtLib25Visitor

import tempfile
import time
import os
from os import listdir, system, kill
from os.path import isfile, join
from signal import alarm, signal, SIGALRM, SIGKILL
from subprocess import PIPE, Popen

def get_process_children(pid):
    p = Popen('ps --no-headers -o pid --ppid %d' % pid, shell = True,stdout = PIPE, stderr = PIPE)
    stdout, stderr = p.communicate()
    return [int(p) for p in stdout.split()]
        
# Run a command with a timeout, after which it will be forcibly killed.
def run(args, cwd = None, shell = False, kill_tree = True, timeout = -1, env = None):
    '''
    Run a command with a timeout after which it will be forcibly
    killed.
    '''
    class Alarm(Exception):
        pass
    def alarm_handler(signum, frame):
        raise Alarm
    p = Popen(args, shell = shell, cwd = cwd, stdout = PIPE, stderr = PIPE, env = env)
    if timeout != -1:
        signal(SIGALRM, alarm_handler)
        alarm(timeout)
    try:
        stdout, stderr = p.communicate()
        stdout = stdout.decode(encoding='ascii')
        stderr = stderr.decode(encoding='ascii')
        if timeout != -1:
            alarm(0)
    except Alarm:
        pids = [p.pid]
        if kill_tree:
            pids.extend(get_process_children(p.pid))
        for pid in pids:
            # process might have died before getting to this line
            # so wrap to avoid OSError: no such process
            try:
                kill(pid, SIGKILL)
            except OSError:
                pass
        return -9, '', ''
    return p.returncode, stdout, stderr

class ResponseVisitor(SmtLib25Visitor):
    def __init__(self):
        self.status = None # will be replaced by 'sat', 'unsat', etc.
        self.errors = []
        self.model = {}
    
    def visitScript(self, ctx):
        raise Exception("attempted to parse a response, got a script")

    def visitCheck_sat_response(self, ctx):
        if self.status is not None:
            raise ValueError("multiple check-sat-response entries not supported")
        response = ctx.getText()
        if response == "sat\n":
            self.status = "sat"
        elif response == "unsat\n":
            self.status = "unsat"
        elif response == "timeout\n":
            self.status = "timeout"
        elif response == "unknown\n":
            self.status = "unknown"
        else:
            raise ValueError("unrecognized check-sat-response " + response)
        return self.visitChildren(ctx)

    def visitError_response(self, ctx):
        self.errors.append(ctx.string().getText())
        return self.visitChildren(ctx)

    def visitGet_model_response(self, ctx):
        for child in ctx.getChildren():
            modelEntry = self.visit(child)
            if modelEntry is not None:
                (varname, assignment) = modelEntry
                self.model[varname] = assignment
        return None

    def visitModel_response(self, ctx):
        return self.visit(ctx.getChild(2))

    def visitFun_def(self, ctx):
        # fun_def : symbol ( sorted_var* ) sort term
        return (ctx.getChild(0).getText(), self.visit(ctx.getChild(ctx.getChildCount() - 1)))

    def visitString(self, ctx):
        return ctx.getText()

    def visitNumeral(self, ctx):
        return ctx.getText()

    def visitIdentifier(self, ctx):
        return ctx.getText()

# Parse an instance and collect all variables declared by (declare-fun), (declare-const), etc.
class InstanceVariableVisitor(SmtLib25Visitor):
    def __init__(self):
        self.variables = []

    def visitResponse(self, ctx):
        raise Exception("attempted to parse a script, got a response")

    def visitCommand(self, ctx):
        cmdtype = ctx.getChild(1).getText()
        if cmdtype == "declare-const" or cmdtype == "declare-fun":
            # SYMBOL is child[2]
            varname = ctx.getChild(2).getText()
            self.variables.append(varname)
        elif cmdtype == "define-fun":
            # SYMBOL is child[2].child[0]
            varname = ctx.getChild(2).getChild(0).getText()
            self.variables.append(varname)

z3_path = "/home/mtrberzi/projects/z3str/build/z3"
z3str2_path = "/home/mtrberzi/projects/z3str/Z3-str/Z3-str.py"
            
def main(argv):
    instancePath = argv[1]
    instream = FileStream(instancePath)
    lexer = SmtLib25Lexer(instream)
    tokenstream = CommonTokenStream(lexer)
    parser = SmtLib25Parser(tokenstream)
    tree = parser.smtfile()
    v = InstanceVariableVisitor()
    v.visit(tree)
    (code, stdout, stderr) = run([z3_path, "-T:20", "dump_models=true", instancePath], timeout=25)
    responseStream = InputStream(stdout)
    responseParser = SmtLib25Parser(CommonTokenStream(SmtLib25Lexer(responseStream)))
    responseTree = responseParser.smtfile()
    responseV = ResponseVisitor()
    responseV.visit(responseTree)
    print(responseV.status)
    if responseV.status == "sat":
        modelAssertions = []
        for var in v.variables:
            if var in responseV.model.keys():
                print(var + " = " + responseV.model[var])
                modelAssertions.append("(assert (= " + var + " " + responseV.model[var] + "))")
        # now open the original instance and copy it to a temporary file,
        # prepending the model assertions when we first see (check-sat)
        checkfilepath = ""
        with open(argv[1], 'r') as inst:
            tmp_f = tempfile.NamedTemporaryFile(mode="w+", suffix=".smt2", delete=False)
            checkfilepath = tmp_f.name
            lines = inst.readlines()
            for line in lines:
                if "set-logic" in line:
                    continue
                if "check-sat" in line:
                    for a in modelAssertions:
                        tmp_f.write(a)
                tmp_f.write(line)
            tmp_f.flush()
            tmp_f.close()
        # verify model with z3str2
        (z3str2_code, z3str2_stdout, z3str2_stderr) = run([z3str2_path, "-f", checkfilepath], timeout=25)
        z3str2_status = None
        for line in z3str2_stdout.split("\n"):
            if "SAT" in line:
                z3str2_status = "sat"
                break
            elif "UNSAT" in line:
                z3str2_status = "unsat"
                break
            elif "UNKNOWN" in line:
                z3str2_status = "unknown"
                break
            else:
                continue
        if z3str2_status is None:
            print("ERROR: could not parse z3str2 output")
            print(z3str2_stdout)
        elif z3str2_status == "sat":
            print("z3str2 status: sat (OK)")
        else:
            print("z3str2 status: " + z3str2_status + " (FAIL)")
        # delete temp file
        os.remove(checkfilepath)
    

if __name__ == '__main__':
    main(sys.argv)

