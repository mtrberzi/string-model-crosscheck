#!/usr/bin/env python3

import sys
from antlr4 import *
from SmtLib25Lexer import SmtLib25Lexer
from SmtLib25Parser import SmtLib25Parser
from SmtLib25Visitor import SmtLib25Visitor

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

def main(argv):
    instream = FileStream(argv[1])
    lexer = SmtLib25Lexer(instream)
    tokenstream = CommonTokenStream(lexer)
    parser = SmtLib25Parser(tokenstream)
    tree = parser.smtfile()
    v = ResponseVisitor()
    v.visit(tree)
    print(v.status)
    print(v.model)
    print(v.errors)

if __name__ == '__main__':
    main(sys.argv)

