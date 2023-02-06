import pyteal as pt
from beaker.lib.storage import List
from beaker.application import Application

options = pt.CompileOptions(version=pt.MAX_TEAL_VERSION, mode=pt.Mode.Application)


def test_list():
    l = List(pt.abi.Uint64, 100, name="l")

    assert l._elements == 100
    assert l._element_size == 8
    assert l._box_size == 8 * 100
    assert l.value_type == pt.abi.Uint64TypeSpec()

    item = l[pt.Int(10)]
    with pt.TealComponent.Context.ignoreExprEquality():
        assert item.name.__teal__(options) == pt.Bytes("l").__teal__(options)
        assert item.element_size.__teal__(options) == pt.Int(8).__teal__(options)
        assert item.idx.__teal__(options) == pt.Int(10).__teal__(options)

    expected, _ = pt.BoxExtract(
        pt.Bytes("l"), pt.Int(8) * pt.Int(10), pt.Int(8)
    ).__teal__(options)
    actual, _ = item.get().__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    val = pt.abi.Uint64()
    expected, _ = pt.BoxReplace(
        pt.Bytes("l"), pt.Int(8) * pt.Int(10), val.encode()
    ).__teal__(options)
    actual, _ = item.set(val).__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_list_app():
    class State:
        l = List(pt.abi.Uint64, 100)

    t = Application("T", state_class=State)

    @t.external
    def get(idx: pt.abi.Uint16, *, output: pt.abi.Uint64):
        return State.l[idx.get()].store_into(output)

    @t.external
    def set(idx: pt.abi.Uint16, val: pt.abi.Uint64):
        return State.l[idx.get()].set(val)

    compiled = t.compile()
    assert compiled.approval_program
