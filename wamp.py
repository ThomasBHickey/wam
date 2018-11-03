#!/usr/bin/env python3

# Copyright Joel Martin <github@martintribe.org>
# Licensed under MPL-2.0 (see ./LICENSE)
# https://github.com/kanaka/wam

from ast import literal_eval
from itertools import chain
from pprint import pprint
import re
import sys

def nth_word(tokens, nth):
    if nth < 0:
        word_cnt = len([e for e in tokens if type(e) != Whitespace])
        nth = word_cnt + nth
    word_idx = 0
    for tok_idx, a in enumerate(tokens):
        if type(a) == Whitespace:
            pass
        elif word_idx == nth:
            return tok_idx, a
        else:
            word_idx += 1

def words(tokens):
    return [e for e in tokens if type(e) != Whitespace]

def _escape(s):
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\x00', '\\00')

#
# Ast node types
#
class Node():
    start = []
    end = []
    def __init__(self, val): self.val = val
    def surround(self, start, end):
        self.start = start
        self.end = end

class List(Node, list):
    def __init__(self, *args, **kwargs):
        list.__init__(self, *args)
        self.words = words(self)
        self.type = 'list'
        self.start = kwargs.get('start', [])
        self.end = kwargs.get('end', [])
    def __add__(self, rhs): return List(list.__add__(self, rhs))
    def __getitem__(self, i):
        if type(i) == slice: return List(list.__getitem__(self, i))
        elif i >= len(self): return None
        else:                return list.__getitem__(self, i)
    def __getslice__(self, *a): return List(list.__getslice__(self, *a))

class Splice(List):
    def __str__(self):
        return '<' + List.__str__(self) + '>'
    pass

class Whitespace(Node, object):
    type = 'whitespace'
    def __repr__(self): return "Whitespace('%s')" % self.val

class Name(Node, object):
    type = 'name'
    def __repr__(self): return "Name(%s)" % self.val

class Literal(Node, object):
    type = 'literal'
    def __repr__(self): return "Literal(%s)" % self.val

class String(Node, object):
    type = 'string'
    def __repr__(self): return "String('%s')" % self.val

class Integer(Node, object):
    type = 'integer'
    def __repr__(self): return "Integer('%s')" % self.val

class Float(Node, object):
    type = 'float'
    def __repr__(self): return "Float('%s')" % self.val

#
# Token reader
#
class Reader():
    def __init__(self, tokens, position=0):
        self.tokens = tokens
        self.position = position
        self.line = 0

    def next(self):
        self.position += 1
        return self.tokens[self.position-1]

    def peek(self):
        if len(self.tokens) > self.position:
            return self.tokens[self.position]
        else:
            return None

# 
# Parsing
#
tokre = re.compile(r"""([\s][\s]*|[(];.*?;[)]|[\[\]{}()`~^@]|'(?:[\\].|[^\\'])*'?|"(?:[\\].|[^\\"])*"?|;;.*|[^\s\[\]{}()'"`@,;]+)""")

def tokenize(str):
    return [t for t in re.findall(tokre, str)]

space_re = re.compile(r"""^([\s]+|;;.*|[(];.*)$""")
def is_whitespace(tok):
    return re.match(space_re, tok)

def read_whitespace(reader):
    res = []
    tok = reader.peek()
    while tok and is_whitespace(tok):
        res.append(Whitespace(reader.next()))
        reader.line += tok.count('\n')
        tok = reader.peek()
    return res

int_re = re.compile(r"-?[0-9xa-fA-F]+$")
float_re = re.compile(r"-?[0-9][0-9.]*$")
def read_atom(reader):
    token = reader.next()
    if token[0] == '$':             return Name(token)
    elif token[0] == '"':           return String(token)
    elif re.match(int_re, token):   return Integer(token)
    elif re.match(float_re, token): return Float(token)
    elif re.match(space_re, token): return Whitespace(token)
    else:                           return Literal(token)

def read_form(reader):
    token = reader.peek()
    # reader macros/transforms
    if token.startswith(';;') or token.startswith('(;'):
        return token

    # list
    elif token == ')': raise Exception("unexpected ')'")
    elif token == '(': return read_list(reader)

    # atom
    else:              return read_atom(reader);

def read_list(reader, start='(', end=')'):
    lst = []

    ws_start = read_whitespace(reader)
    token = reader.next()
    if token != start: raise Exception("expected '" + start + "'")

    token = reader.peek()
    while token != end:
        if not token: raise Exception("expected '" + end + "', got EOF")
        lst.append(read_form(reader))
        lst.extend(read_whitespace(reader))
        token = reader.peek()
    reader.next()
    ws_end = read_whitespace(reader)
    ast = List(lst, start=ws_start, end=ws_end)
    return ast

def read_str(str):
    tokens = tokenize(str)
    if len(tokens) == 0: raise Blank("Blank Line")
    reader = Reader(tokens)
    ast = read_list(reader)
    return ast

# 
# macros
#

# Short circuiting logical comparisons
def AND(args, ctx):
    assert len(args) > 0, "AND takes at least 1 argument"
    res = List([Literal('i32.const'), Integer(1)])
    for arg in reversed(args):
        a = eval(arg, ctx)
        # TODO: make whitespace optional here and above
        res = List([Literal('if'), Literal('i32'), a,
                    res, List([Literal('i32.const'), Integer(0)])])
    return res

def OR(args, ctx):
    assert len(args) > 0, "OR takes at least 1 argument"
    res = List([Literal('i32.const'), Integer(0)])
    for arg in reversed(args):
        a = eval(arg, ctx)
        # TODO: make whitespace optional here and above
        res = List([Literal('if'), Literal('i32'), a,
                    List([Literal('i32.const'), Integer(1)]), res])
    return res

def CHR(args, ctx):
    assert len(args) == 1, "CHR takes 1 argument"
    arg1 = args[0].val
    c = literal_eval(arg1)
    if len(c) != 1:
        raise Exception("Invalid CHR macro, must be 1 character string")
    return read_str("(i32.const 0x%x (; %s ;))" % (ord(c), arg1))

def STRING(args, ctx):
    s = literal_eval(args[0].val)
    if s in ctx.string_map:
        # Duplicate string, re-use address
        sname = ctx.string_map[s]
    else:
        sname = "$S_STRING_%d" % len(ctx.strings)
        ctx.strings.append([sname, s])
        ctx.string_map[s] = sname
    return read_str("(i32.add (get_global $memoryBase) (get_global %s))" % sname)

def STATIC_ARRAY(args, ctx):
    assert len(args) == 1, "STATIC_ARRAY takes 1 argument"
    slen = int(literal_eval(args[0].val))
    sname = "$S_STATIC_ARRAY_%d" % len(ctx.strings)
    ctx.strings.append([sname, slen])
    return read_str("(i32.add (get_global $memoryBase) (get_global %s))" % sname)

def LET(args, ctx):
    assert len(args) >= 2, "LET takes at least 2 argument"
    assert len(args) % 2 == 0, "LET takes even number of argument"
    locals = [Literal('local')]
    sets = []
    for i in range(0, len(args), 2):
        name = args[i]
        res = eval(args[i+1], ctx)
        res.surround([], [])
        locals.extend([name, Literal('i32')])
        sets.append(List([Literal('set_local'), name, res]))
    # return a Splice so that it items get spliced in
    return Splice([List(locals)] + sets)

macros = {
    'AND': AND,
    'OR': OR,
    'CHR': CHR,
    'STRING': STRING,
    'STATIC_ARRAY': STATIC_ARRAY,
    'LET': LET
}

#
# eval / macro expansion
#

EVAL_HOIST = ('global', 'table')
EVAL_NONE = ('memory', 'import', 'export', 'type',
            'get_global', 'local', 'get_local', 'param', 'br',
            'i32.const', 'i64.const', 'f32.const', 'f64.const')
EVAL_REST = ('module', 'func', 'memory', 'call', 'set_local',
             'set_global', 'block', 'loop', 'br_if')
EVAL_LAST = ('global', 'br_table')

def eval(ast, ctx):
    if type(ast) == List:
        a0idx, a0 = nth_word(ast,0)
        a0type = type(a0)
        if a0type == Name:
            # if first word is a $name, make it a call and evaluate the
            # rest of the list
            lst = [eval(e, ctx) for e in ast[a0idx+1:]]
            lst = [Literal('call'), a0] + lst
        elif a0type == Literal and a0.val in macros:
            # expand macros
            res = macros[ast[0].val](ast.words[a0idx+1:], ctx)
            if type(res) == Splice:
                for r in res: r.surround(ast.start, ast.end)
            else:
                res.surround(ast.start, ast.end)
            return res
        elif a0type == Literal and a0.val in EVAL_HOIST:
            # Hoist globals and table to the top
            # TODO: this shouldn't be necessary if wasm-as was
            # compliant with the spec which indicates that any
            # ordering should be sufficient
            if a0.val in EVAL_LAST:
                # eval last argument
                idx, a = nth_word(ast, -1)
                ast[idx] = eval(a, ctx)
            ws = Whitespace("(; %s %s hoisted to top ;)" % (
                a0.val, ast.words[1].val))
            ws.surround(ast.start, ast.end)
            ast.surround([Whitespace('  ')], [Whitespace('\n')])
            ctx.hoist.append(ast)
            return ws
        elif a0type == Literal and a0.val in EVAL_NONE:
            # don't eval arguments
            return ast
        elif a0type == Literal and a0.val in EVAL_REST:
            # don't eval first argument if it's a name
            idx, a = nth_word(ast, 1)
            if type(a) == Name:
                idx, a = nth_word(ast, 2)
            lst = ast[:idx] + [eval(e, ctx) for e in ast[idx:]]
        elif a0type == Literal and a0.val in EVAL_LAST:
            # only eval last argument
            idx, a = nth_word(ast, -1)
            ast[idx] = eval(a, ctx)
            return ast
        else:
            # evaluate all elements
            lst = [eval(e, ctx) for e in ast]
        res_lst = []
        for l in lst:
            if type(l) == Splice: res_lst.extend(l)
            else:                 res_lst.append(l)
        return List(res_lst, start=ast.start, end=ast.end)
    elif type(ast) == String:
        # Pass raw strings to the STRING macro
        return STRING([ast], ctx)
    elif type(ast) == Integer:
        return List([Literal('i32.const'), ast])
    elif type(ast) == Float:
        return List([Literal('f32.const'), ast])
    elif type(ast) == Name:
        return List([Literal('get_local'), ast])
    else:
        return ast

# 
# emit
#

def emit(ast, ctx):
    toks = []
    # Prepend leading whitespace
    for a in ast.start: toks.extend(emit(a, ctx))
    if type(ast) == List:
        if len(ast.words) > 1 and ast.words[0].val == 'module':
            mname = ast.words[1].val[1:]
            ctx.modules.append(mname)
            toks.append(';; module $%s\n' % mname)
            mode = 'skip'
            for a in ast:
                # skip module and module name
                if mode == 'skip':
                    if type(a) == List:
                        mode = 'continue'
                    elif type(a) == Literal and a.val == 'module':
                        continue
                    elif type(a) == Name:
                        continue
                toks.extend(emit(a, ctx))
        else:
            toks.append('(')
            for a in ast:
                r = emit(a, ctx)
                # add whitespace between list items if needed
                if (toks[-1] != '('
                        and not is_whitespace(toks[-1])
                        and not is_whitespace(r[0])):
                    toks.append(' ')
                toks.extend(r)
            toks.append(')')
    elif type(ast) in [Integer, Float]:
        toks.append(str(ast.val))
    elif type(ast.val) == str:
        toks.append(ast.val)
    else:
        raise Exception("type %s has non-string val: %s" % (
            type(ast.val), ast.val))
    # Append trailing whitespace
    for a in ast.end: toks.extend(emit(a, ctx))
    return toks

def emit_module(asts, ctx, memorySize=256):
    mod_tokens = []
    for ast in asts:
        mod_tokens.extend(emit(ast, ctx))

        # Create data section with static strings
        strings = ctx.strings
        string_tokens = []
        if strings:
            # static string/array names/pointers
            string_offset = 0
            for (name, data) in strings:
                if type(data) == int:
                    slen = data+1
                else:
                    slen = len(data)+1
                string_tokens.append('  (global %s  i32 (i32.const %d))\n' % (
                    name, string_offset))
                string_offset += slen

            # Terminator so we know how much memory we took
            string_tokens.append(
                    '  (global $S_STRING_END  i32 (i32.const %d))\n\n' % (
                string_offset))

            # static string/array data
            string_tokens.append("  (data\n    (get_global $memoryBase)\n")
            string_offset = 0
            for name, data in strings:
                if type(data) == int:
                    sdata = ("\x00"*data)
                else:
                    sdata = data
                slen = len(sdata)+1
                string_tokens.append('    %-30s ;; %d\n' % (
                    '"'+_escape(sdata)+'\\00"', string_offset))
                string_offset += slen
            string_tokens.append("  )\n\n")


    all_tokens = [
            "(module $%s\n\n" % "__".join(ctx.modules),
            "  (import \"env\" \"memory\" (memory %d))\n" % memorySize,
            "  (import \"env\" \"memoryBase\" (global $memoryBase i32))\n\n"
            ]
    # Hoisted global defintions
    all_tokens.extend(chain(*[emit(h, ctx) for h in ctx.hoist]))
    all_tokens.append("\n")
    # Static string/array defintions and pointers
    all_tokens.extend(string_tokens)
    all_tokens.append("\n")
    # Rest of the module
    all_tokens.extend(mod_tokens)
    all_tokens.append("\n)")

    #pprint(all_tokens, stream=sys.stderr)
    return "".join(all_tokens)

def empty_ctx():
    return type('', (), {
        'hoist': [],
        'strings': [],
        'string_map': {},
        'modules': []})

