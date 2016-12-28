ANTLRPATH="/opt/antlr-4.6-complete.jar"
antlr4=java -jar $(ANTLRPATH)
ANTLR_GENERATED_FILES=SmtLib25Lexer.py SmtLib25Lexer.tokens SmtLib25Listener.py SmtLib25Parser.py SmtLib25Visitor.py SmtLib25.tokens

all: SmtLib25.g4
	$(antlr4) -Dlanguage=Python3 -visitor SmtLib25.g4

clean:
	rm -f $(ANTLR_GENERATED_FILES)

