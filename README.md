# wam: WebAssembly Macro language and processor

## wam syntax

Wam syntax is a near superset of wast syntax that is more convenient
for human developers to write directly.

The one place where wam is not a strict superset of wast 
is that it does not supports numeric indexes for globals, functions,
and local references. But this is okay because index based references
are much less useful to humans than they are to computers.

The following extensions to the wast syntax are supported:

- The call operation can be omitted if the function is specified by 
  name. 
- i32 and f32 constants can be specified directly without wrapping
  with "i32.const" or "f32.const". Floating point literals must
  include a decimal point.
- Local variables can be specified directly without wrapping with
  "get\_local".
- Static strings can be specified inline. All static strings in the
  code will be de-duplicated, they will be added to a global data
  section, pointer variables will be created that index into the data
  section and the original static inline string will be replaced with
  a lookup relative to $memoryBase.
- AND and OR macros that implement i32 boolean logic operations which
  support 1 or more conditions and that are short-circuiting.
- STATIC\_ARRAY macro that allocates the specified number of bytes as
  a static array in the data section. Note this creates an static
  global array at build time not at runtime (i.e. it does not
  dynamically allocate memory).
- CHR macro that converts a 1 byte string into a character (i32.const)
  value.
- LET macro that combines functionality from "locals" and
  "set\_local" into a single construct that allow more concise
  declaration and initialization of i32 values.

## wamp: wam processor

Current functionality:

- Processes wam syntax into standard wast syntax support.
- Automatically adds memory and memoryBase imports. Memory size
  defaults to 256 but can be changed via --memorySize parameter.
- Supports combining multiple modules into a single module.
- Retains whitespace and comments from original wam file(s).
- Implemented as a small JavaScript/Node program that should be fairly
  easy to extend with additional macro definitions.

Future functionality:

- Add elif construct
- Allow bare names for global variables by implementing some limited
  lexical scope.
- Resolving/linking of imports and exports across multiple files.

## Example

In the `examples/` directory is a fizzbuzz example that makes use of
wam syntax. Use `wamp` to convert the example to wast source.

```
./wamp examples/fizzbuzz.wam examples/print.wam > fizzbuzz.wast
```

Examine the wam files and the resulting wast to see what processing
and macro expansion was performanced by `wamp`. The wast source can be
compiled to a wasm module using the `wasm-as` assembler from
[binaryen](https://github.com/WebAssembly/binaryen).

```
wasm-as fizzbuzz.wast -o fizzbuzz.wasm
```

The wasm module can be executed using the
[wac/wace](https://github.com/kanaka/wac) WebAssembly interpreter:

```
wace ./fizzbuzz.wasm
```


## Examples of wam and equivalent wast:

| wam | wast |
| --- | ---- |
| <pre>($myfun)</pre>    | <pre>(call $myfun)</pre> |
| <pre>7</pre>           | <pre>(i32.const 7)</pre> |
| <pre>$myvar</pre>      | <pre>(get\_local $myvar)</pre> |
| <pre>(CHR "A")</pre>   | <pre>(i32.const 0x40)</pre> |
| <pre>"my string"</pre> | <pre>(global $S_STRING_7  i32 (i32.const 73))<br>(data ... "my string\00" ...)<br>...<br>(i32.add (get\_global $memoryBase)<br>         (get\_global $S\_STRING\_7))</pre> |
| <pre>(AND 7 8)</pre>   | <pre>(if i32 (i32.const 7)<br>  (if i32 (i32.const 8) (i32.const 1) (i32.const 0))<br>  (i32.const 0))</pre> |
| <pre>(OR 7 8)</pre>    | <pre>(if i32 (i32.const 7)<br>  (i32.const 1)<br>  (if i32 (i32.const 8) (i32.const 1) (i32.const 0)))</pre> |
| <pre>(LET $i 7<br>     $j (i32.add $i 1))</pre> | <pre>(local $i i32 $j i32)<br>(set_local $i (i32.const 7)<br>(set_local $j (i32.add (get_local $i) (i32.const 1)))</pre> |


## License

MPL-2.0 (see `./LICENSE`)
