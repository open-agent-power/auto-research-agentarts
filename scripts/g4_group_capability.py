"""Bounded interpreter for one reviewed group-label helper, never Python execution.

This fixed host module parses code as data and interprets a closed AST subset.
It does not import candidate modules or call eval/exec/compile. It exposes no IO,
network, process, reflection or project mutation operation to a helper. This is
a computational capability boundary, not an OS or same-user filesystem sandbox.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
import ast
import hashlib
import json
import re

MAX_SOURCE_BYTES = 16_384
MAX_AST_NODES = 512
MAX_AST_DEPTH = 32
MAX_LOOP_DEPTH = 2
MAX_ROWS = 2048
MAX_GROUP_FIELDS = 4
MAX_LABEL_CHARS = 128
MAX_BINDINGS = 64
MAX_STEPS = 5_000_000
MAX_ALLOCATED_CELLS = 262_144
MAX_SCALAR_WORK = 64_000_000
BUILTINS = frozenset({"list", "dict", "len", "enumerate"})
METHODS = frozenset({"index", "append", "get", "setdefault", "fromkeys"})


class CapabilityError(ValueError):
    def __init__(self, code, message, usage=None):
        super().__init__(message)
        self.code = code
        self.usage = usage


def _require(condition, code, message):
    if not condition:
        raise CapabilityError(code, message)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Limits:
    steps: int = MAX_STEPS
    allocated_cells: int = MAX_ALLOCATED_CELLS
    scalar_work: int = MAX_SCALAR_WORK

    def checked(self):
        for name, maximum in (("steps", MAX_STEPS), ("allocated_cells", MAX_ALLOCATED_CELLS),
                              ("scalar_work", MAX_SCALAR_WORK)):
            value = getattr(self, name)
            _require(type(value) is int and 1 <= value <= maximum, "INVALID_LIMIT",
                     "Host limits may only lower the fixed positive ceilings.")
        return self


_ALLOWED = frozenset({ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Assign,
    ast.Return, ast.For, ast.If, ast.Expr, ast.Name, ast.Subscript, ast.Attribute,
    ast.Call, ast.Constant, ast.List, ast.Dict, ast.ListComp, ast.DictComp,
    ast.comprehension, ast.Compare, ast.UnaryOp, ast.Tuple, ast.Load, ast.Store,
    ast.In, ast.NotIn, ast.Eq, ast.NotEq, ast.Not, ast.USub})


def _source_bytes(source):
    _require(type(source) in (str, bytes), "INVALID_SOURCE", "Source must be text or UTF-8 bytes.")
    _require(0 < len(source) <= MAX_SOURCE_BYTES, "SOURCE_LIMIT", "Source length exceeds the byte/codepoint precheck.")
    try:
        raw = source.encode("utf-8") if type(source) is str else source
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        raise CapabilityError("INVALID_SOURCE", "Source must be strict UTF-8.") from None
    _require(0 < len(raw) <= MAX_SOURCE_BYTES and "\x00" not in text,
             "SOURCE_LIMIT", "Source is empty, contains NUL, or exceeds the byte ceiling.")
    return raw


def _target_names(target):
    if type(target) is ast.Name:
        return [target.id]
    _require(type(target) is ast.Tuple and len(target.elts) == 2
             and all(type(item) is ast.Name for item in target.elts),
             "INVALID_TARGET", "Loop unpacking supports exactly two simple names.")
    return [item.id for item in target.elts]


@lru_cache(maxsize=32)
def _prepare(raw):
    # AST parsing builds syntax data; it does not execute or compile a helper.
    try:
        module = ast.parse(raw.decode("utf-8"), mode="exec")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        raise CapabilityError("INVALID_SYNTAX", "Helper source could not be parsed.") from None
    _require(len(module.body) == 1 and type(module.body[0]) is ast.FunctionDef,
             "MODULE_SHAPE", "Exactly one helper definition is allowed.")
    fn = module.body[0]
    args = fn.args
    _require(fn.name == "encode_groups" and not fn.decorator_list and fn.returns is None
             and not getattr(fn, "type_params", []) and fn.type_comment is None
             and not args.posonlyargs and len(args.args) == 1 and args.args[0].arg == "labels"
             and args.args[0].annotation is None and args.args[0].type_comment is None
             and args.vararg is None and args.kwarg is None and not args.kwonlyargs
             and not args.defaults and not args.kw_defaults,
             "SIGNATURE", "Use exactly def encode_groups(labels), without defaults or annotations.")
    bindings = set()
    count = 0
    pending = [(module, None, 0, 0)]
    while pending:
        node, parent, depth, loops = pending.pop()
        count += 1
        _require(count <= MAX_AST_NODES and depth <= MAX_AST_DEPTH, "AST_LIMIT", "AST size/depth ceiling exceeded.")
        _require(type(node) in _ALLOWED, "FORBIDDEN_SYNTAX", "Unsupported AST node: " + type(node).__name__)
        if type(node) is ast.FunctionDef:
            _require(node is fn, "FORBIDDEN_SYNTAX", "Nested function definitions are forbidden.")
        nested = loops + int(type(node) in (ast.For, ast.ListComp, ast.DictComp))
        _require(nested <= MAX_LOOP_DEPTH, "LOOP_DEPTH", "At most two bounded loop levels are allowed.")
        if type(node) is ast.Name:
            _require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", node.id) is not None
                     and "__" not in node.id and node.id != "encode_groups",
                     "FORBIDDEN_NAME", "Invalid, dunder, or recursive name.")
            if type(node.ctx) is ast.Store:
                _require(node.id not in BUILTINS | {"labels"}, "READONLY_NAME", "Input and builtin names cannot be rebound.")
                bindings.add(node.id)
        if type(node) is ast.Constant:
            docstring = (type(node.value) is str and type(parent) is ast.Expr
                         and bool(fn.body) and parent is fn.body[0])
            _require((docstring and len(node.value) <= 512)
                     or node.value is None or type(node.value) is bool
                     or (type(node.value) is int and abs(node.value) <= MAX_ROWS),
                     "CONSTANT_TYPE", "Only small integer/bool/None constants and an optional short docstring are allowed.")
        if type(node) is ast.Attribute:
            _require(type(parent) is ast.Call and parent.func is node and type(node.value) is ast.Name
                     and node.attr in METHODS, "FORBIDDEN_ATTRIBUTE", "Only fixed container operations may be called.")
        if type(node) is ast.Call:
            _require(not node.keywords and not any(type(a) is ast.Starred for a in node.args),
                     "CALL_SHAPE", "Keywords and argument expansion are not supported.")
            _require((type(node.func) is ast.Name and node.func.id in BUILTINS)
                     or type(node.func) is ast.Attribute, "FORBIDDEN_CALL", "Only fixed container intrinsics are callable.")
            if type(node.func) is ast.Name and node.func.id == "enumerate":
                _require(type(parent) in (ast.For, ast.comprehension) and parent.iter is node,
                         "ENUMERATE_POSITION", "enumerate is available only directly as a loop source.")
        if type(node) is ast.Dict:
            _require(all(key is not None for key in node.keys), "DICT_EXPANSION", "Dictionary expansion is forbidden.")
        if type(node) is ast.Assign:
            _require(len(node.targets) == 1 and type(node.targets[0]) in (ast.Name, ast.Subscript)
                     and node.type_comment is None, "INVALID_TARGET", "Use one simple name or dictionary-cell target.")
        if type(node) is ast.Subscript:
            _require(type(node.value) is ast.Name, "SUBSCRIPT_SHAPE", "Subscript owner must be a simple bound name.")
        if type(node) is ast.Tuple:
            _require(type(node.ctx) is ast.Store and type(parent) in (ast.For, ast.comprehension)
                     and parent.target is node, "TUPLE_SHAPE", "Tuples are reserved for loop unpacking.")
        if type(node) is ast.For:
            _target_names(node.target)
            _require(not node.orelse and node.type_comment is None, "LOOP_SHAPE", "For-else is not supported.")
        if type(node) in (ast.ListComp, ast.DictComp):
            _require(len(node.generators) == 1 and not node.generators[0].is_async
                     and len(node.generators[0].ifs) <= 2, "COMPREHENSION_SHAPE", "Use one finite generator with at most two filters.")
            _target_names(node.generators[0].target)
        if type(node) is ast.Compare:
            _require(len(node.ops) == len(node.comparators) == 1,
                     "COMPARE_SHAPE", "Only one membership/equality comparison is supported.")
        if type(node) is ast.Expr:
            _require(type(node.value) is ast.Call or (node is fn.body[0] and type(node.value) is ast.Constant
                     and type(node.value.value) is str), "EXPRESSION_STATEMENT", "Only intrinsic calls or a leading docstring are statements.")
        pending.extend((child, node, depth + 1, nested) for child in ast.iter_child_nodes(node))
    _require(len(bindings) <= MAX_BINDINGS, "BINDING_LIMIT", "Too many local names.")
    return fn, count, _sha(ast.dump(module, include_attributes=False).encode("utf-8"))


def validate_group_program(source):
    """Validate syntax without running even one helper operation."""
    raw = _source_bytes(source)
    _, count, ast_sha = _prepare(raw)
    return {"schema_version": "g4-group-program-validation-v1", "source_sha256": _sha(raw),
            "ast_sha256": ast_sha, "ast_nodes": count, "function": "encode_groups", "executed": False}


@dataclass(frozen=True)
class _Input:
    values: tuple


@dataclass(frozen=True)
class _Enumerated:
    values: tuple
    owner: int | None


class _Return(Exception):
    def __init__(self, value):
        self.value = value


def _is_label(value):
    return (type(value) is tuple and 1 <= len(value) <= MAX_GROUP_FIELDS
            and all(type(part) is str and len(part) <= MAX_LABEL_CHARS for part in value))


def _is_cell(value):
    return value is None or (type(value) is int and abs(value) <= MAX_ROWS) or _is_label(value)


class _Interpreter:
    def __init__(self, limits):
        self.limits = limits.checked()
        self.usage = {"steps": 0, "allocated_cells": 0, "scalar_work": 0}
        self.active = {}

    def charge(self, name="steps", count=1):
        _require(count <= getattr(self.limits, name) - self.usage[name],
                 "BUDGET_EXHAUSTED", name + " ceiling exceeded.")
        self.usage[name] += count

    def label_key(self, value):
        _require(_is_label(value), "DICT_KEY_TYPE", "Dictionary keys must be primitive group-label tuples.")
        self.charge("scalar_work", 1 + sum(map(len, value)))
        return value

    def same(self, left, right):
        _require(_is_cell(left) and _is_cell(right), "COMPARE_TYPE", "Compare only scalar cells or group labels.")
        work = sum(1 + sum(map(len, v)) if _is_label(v) else 1 for v in (left, right))
        self.charge("scalar_work", work)
        self.charge()
        return left == right

    def put(self, env, target, value):
        if type(target) is ast.Name:
            _require(target.id not in BUILTINS | {"labels"}
                     and len(env) + int(target.id not in env) <= MAX_BINDINGS + 1,
                     "BINDING_LIMIT", "Local binding is readonly or exceeds its ceiling.")
            if target.id not in env:
                self.charge("allocated_cells")
            env[target.id] = value
            return
        if type(target) is ast.Tuple:
            _require(type(value) is tuple and len(value) == 2, "UNPACK_TYPE", "Unpack a finite enumerate pair only.")
            for name, item in zip(target.elts, value):
                self.put(env, name, item)
            return
        owner = self.expr(target.value, env)
        _require(type(owner) is dict, "WRITE_TYPE", "Only dictionary cells can be assigned.")
        self.dict_set(owner, self.expr(target.slice, env), value)

    def writable(self, value):
        _require(not self.active.get(id(value)), "ITERATION_MUTATION", "Cannot mutate a container being iterated.")

    @staticmethod
    def truth(value):
        if type(value) in (_Input, _Enumerated):
            return bool(value.values)
        return bool(value)

    def dict_set(self, owner, key, value):
        key = self.label_key(key)
        _require(value is None or (type(value) is int and abs(value) <= MAX_ROWS),
                 "DICT_VALUE_TYPE", "Dictionary values must be bounded integers or None.")
        self.writable(owner)
        if key not in owner:
            _require(len(owner) < MAX_ROWS, "CONTAINER_LIMIT", "Dictionary ceiling exceeded.")
            self.charge("allocated_cells", 2)
        owner[key] = value

    def append(self, owner, value):
        _require(type(owner) is list and _is_cell(value), "LIST_CELL_TYPE", "Lists contain scalar cells or group labels only.")
        self.writable(owner)
        _require(len(owner) < MAX_ROWS, "CONTAINER_LIMIT", "List ceiling exceeded.")
        self.charge("allocated_cells")
        owner.append(value)

    def sequence(self, value):
        if type(value) is _Input:
            return value.values, None
        if type(value) is _Enumerated:
            return value.values, value.owner
        _require(type(value) in (list, dict) and len(value) <= MAX_ROWS,
                 "ITERABLE_TYPE", "Loop sources must be bounded input/list/dictionary/enumerate values.")
        self.charge("allocated_cells", len(value))
        return tuple(value), id(value)

    @contextmanager
    def iteration(self, value):
        values, owner = self.sequence(value)
        if owner is not None:
            self.active[owner] = self.active.get(owner, 0) + 1
        try:
            yield values
        finally:
            if owner is not None:
                self.active[owner] -= 1

    def call(self, node, env):
        args = [self.expr(arg, env) for arg in node.args]
        if type(node.func) is ast.Name:
            name = node.func.id
            if name == "dict":
                _require(not args, "ARITY", "dict takes no arguments.")
                self.charge("allocated_cells")
                return {}
            if name == "list":
                _require(len(args) <= 1, "ARITY", "list takes zero or one bounded sequence.")
                self.charge("allocated_cells")
                result = []
                if args:
                    with self.iteration(args[0]) as values:
                        for item in values:
                            self.charge()
                            self.append(result, item)
                return result
            _require(len(args) == 1, "ARITY", name + " takes exactly one argument.")
            if name == "len":
                value = args[0]
                _require(type(value) in (_Input, _Enumerated, list, dict), "LEN_TYPE", "len requires a bounded sequence or dictionary.")
                return len(value.values) if type(value) in (_Input, _Enumerated) else len(value)
            values, owner = self.sequence(args[0])
            self.charge("allocated_cells", 2 * len(values))
            return _Enumerated(tuple(enumerate(values)), owner)
        receiver, method = node.func.value.id, node.func.attr
        if receiver == "dict":
            _require(method == "fromkeys" and 1 <= len(args) <= 2, "INTRINSIC", "Only dict.fromkeys(sequence[, integer]) is available.")
            self.charge("allocated_cells")
            result = {}
            default = args[1] if len(args) == 2 else None
            with self.iteration(args[0]) as values:
                for key in values:
                    self.charge()
                    self.dict_set(result, key, default)
            return result
        owner = self.expr(node.func.value, env)
        if type(owner) is list:
            _require(len(args) == 1 and method in ("index", "append"), "INTRINSIC", "Lists expose index(value) and append(value) only.")
            if method == "append":
                self.append(owner, args[0])
                return None
            for index, value in enumerate(owner):
                if self.same(value, args[0]):
                    return index
            raise CapabilityError("INDEX_MISSING", "Requested scalar is absent from the list.")
        _require(type(owner) is dict and method in ("get", "setdefault") and 1 <= len(args) <= 2,
                 "INTRINSIC", "Dictionaries expose get/setdefault only.")
        key = self.label_key(args[0])
        default = args[1] if len(args) == 2 else None
        _require(default is None or (type(default) is int and abs(default) <= MAX_ROWS),
                 "DICT_VALUE_TYPE", "Dictionary defaults must be bounded integers or None.")
        if method == "setdefault" and key not in owner:
            self.dict_set(owner, key, default)
        return owner.get(key, default)

    def expr(self, node, env):
        self.charge()
        kind = type(node)
        if kind is ast.Constant:
            return node.value
        if kind is ast.Name:
            _require(node.id in env, "UNBOUND_NAME", "Name is not a local primitive value: " + node.id)
            return env[node.id]
        if kind is ast.List:
            self.charge("allocated_cells")
            result = []
            for item in node.elts:
                self.append(result, self.expr(item, env))
            return result
        if kind is ast.Dict:
            self.charge("allocated_cells")
            result = {}
            for key, value in zip(node.keys, node.values):
                _require(key is not None, "DICT_EXPANSION", "Dictionary expansion is forbidden.")
                self.dict_set(result, self.expr(key, env), self.expr(value, env))
            return result
        if kind is ast.Call:
            return self.call(node, env)
        if kind is ast.Subscript:
            owner, key = self.expr(node.value, env), self.expr(node.slice, env)
            if type(owner) is dict:
                key = self.label_key(key)
                _require(key in owner, "KEY_MISSING", "Requested group key is absent.")
                return owner[key]
            values = owner.values if type(owner) is _Input else owner
            _require(type(values) is list and type(key) is int and -len(values) <= key < len(values)
                     or type(owner) is _Input and type(key) is int and -len(values) <= key < len(values),
                     "SUBSCRIPT_TYPE", "Index a bounded list/input using an in-range integer.")
            return values[key]
        if kind is ast.UnaryOp:
            value = self.expr(node.operand, env)
            if type(node.op) is ast.Not:
                return not self.truth(value)
            _require(type(value) is int and abs(value) <= MAX_ROWS, "INTEGER_TYPE", "Unary minus requires a bounded integer.")
            return -value
        if kind is ast.Compare:
            left, right = self.expr(node.left, env), self.expr(node.comparators[0], env)
            if type(node.ops[0]) in (ast.Eq, ast.NotEq):
                equal = self.same(left, right)
                return equal if type(node.ops[0]) is ast.Eq else not equal
            if type(right) is dict:
                present = self.label_key(left) in right
            else:
                with self.iteration(right) as values:
                    present = any(self.same(left, item) for item in values)
            return present if type(node.ops[0]) is ast.In else not present
        if kind in (ast.ListComp, ast.DictComp):
            generator = node.generators[0]
            self.charge("allocated_cells")
            result = [] if kind is ast.ListComp else {}
            with self.iteration(self.expr(generator.iter, env)) as values:
                for item in values:
                    self.charge()
                    self.charge("allocated_cells", len(env))
                    local = env.copy()
                    self.put(local, generator.target, item)
                    if not all(self.truth(self.expr(test, local)) for test in generator.ifs):
                        continue
                    if kind is ast.ListComp:
                        self.append(result, self.expr(node.elt, local))
                    else:
                        self.dict_set(result, self.expr(node.key, local), self.expr(node.value, local))
            return result
        raise CapabilityError("FORBIDDEN_EXPRESSION", "Expression is outside the capability language.")

    def statements(self, statements, env):
        for node in statements:
            self.charge()
            if type(node) is ast.Assign:
                self.put(env, node.targets[0], self.expr(node.value, env))
            elif type(node) is ast.Return:
                _require(node.value is not None, "RETURN_TYPE", "Return an explicit list.")
                raise _Return(self.expr(node.value, env))
            elif type(node) is ast.Expr:
                if not (type(node.value) is ast.Constant and type(node.value.value) is str):
                    self.expr(node.value, env)
            elif type(node) is ast.If:
                self.statements(node.body if self.truth(self.expr(node.test, env)) else node.orelse, env)
            elif type(node) is ast.For:
                with self.iteration(self.expr(node.iter, env)) as values:
                    for item in values:
                        self.charge()
                        self.put(env, node.target, item)
                        self.statements(node.body, env)
            else:
                raise CapabilityError("FORBIDDEN_STATEMENT", "Statement is outside the capability language.")


def execute_group_program(source, labels, *, limits=None):
    """Interpret one helper on copied primitive labels and return a complete receipt.

    These labels have already been chosen by a trusted host. This function never
    reads a source path, case, budget ledger or candidate-selected external file.
    A syntactically valid helper may return wrong IDs: semantic equivalence is an
    independent evaluator's job, separate from this capability boundary.
    """
    raw = _source_bytes(source)
    fn, _, ast_sha = _prepare(raw)
    _require(type(labels) in (list, tuple) and len(labels) <= MAX_ROWS, "INPUT_ROWS", "Use at most 2048 primitive group labels.")
    for label in labels:
        _require(type(label) in (list, tuple) and 1 <= len(label) <= MAX_GROUP_FIELDS
                 and all(type(part) is str and len(part) <= MAX_LABEL_CHARS for part in label),
                 "INPUT_LABEL", "Each label has 1..4 exact strings of at most 128 codepoints.")
        try:
            for part in label:
                part.encode("utf-8", errors="strict")
        except UnicodeError:
            raise CapabilityError("INPUT_LABEL_ENCODING", "Label strings must be encodable as strict UTF-8.") from None
    _require(limits is None or type(limits) is Limits, "INVALID_LIMIT", "Use fixed host Limits only.")
    interpreter = _Interpreter(limits if limits is not None else Limits())
    try:
        interpreter.charge("allocated_cells", len(labels) + sum(map(len, labels)))
        copied = tuple(tuple(part for part in label) for label in labels)
        env = {"labels": _Input(copied)}
        try:
            interpreter.statements(fn.body, env)
        except _Return as returned:
            output = returned.value
        else:
            raise CapabilityError("MISSING_RETURN", "Helper must return a list of group IDs.")
        _require(type(output) is list and len(output) == len(copied)
                 and all(type(value) is int and 0 <= value < len(copied) for value in output),
                 "OUTPUT_TYPE", "Return one nonnegative bounded integer ID per input label.")
        return {"schema_version": "g4-group-capability-execution-v1", "status": "completed",
                "source_sha256": _sha(raw), "ast_sha256": ast_sha,
                "input_sha256": _sha(_canonical(copied)), "output_sha256": _sha(_canonical(output)),
                "group_ids": output.copy(), "usage": interpreter.usage.copy(),
                "limits": {key: getattr(interpreter.limits, key) for key in interpreter.usage},
                "product_model_calls": 0, "fit_calls": 0,
                "isolation": "closed_operation_interpreter_not_os_sandbox"}
    except CapabilityError as error:
        error.usage = interpreter.usage.copy()
        raise
