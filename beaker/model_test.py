import pytest
from typing import Literal
import pyteal as pt
from beaker.model import Model


def test_valid_create():
    with pytest.raises(Exception):
        Model()

    with pytest.raises(Exception):

        class A(Model):
            a: pt.abi.Uint64

        class B(A):
            b: pt.abi.Uint64

        B()


class UserId(Model):
    user: pt.abi.Address
    id: pt.abi.Uint64


class Order(Model):
    items: pt.abi.DynamicArray[pt.abi.String]
    id: pt.abi.Uint32
    flags: pt.abi.StaticArray[pt.abi.Bool, Literal[32]]


class SubOrder(Model):
    order: Order
    idx: pt.abi.Uint8


MODEL_TESTS = [
    (
        UserId(),
        pt.abi.Tuple2[pt.abi.Address, pt.abi.Uint64],
        ["user", "id"],
        {"user": pt.abi.Address().type_spec(), "id": pt.abi.Uint64().type_spec()},
        "(address,uint64)",
    ),
    (
        Order(),
        pt.abi.Tuple3[
            pt.abi.DynamicArray[pt.abi.String],
            pt.abi.Uint32,
            pt.abi.StaticArray[pt.abi.Bool, Literal[32]],
        ],
        ["items", "id", "flags"],
        {
            "items": pt.abi.make(pt.abi.DynamicArray[pt.abi.String]).type_spec(),
            "id": pt.abi.Uint32().type_spec(),
            "flags": pt.abi.make(
                pt.abi.StaticArray[pt.abi.Bool, Literal[32]]
            ).type_spec(),
        },
        "(string[],uint32,bool[32])",
    ),
    (
        SubOrder(),
        pt.abi.Tuple2[
            pt.abi.Tuple3[
                pt.abi.DynamicArray[pt.abi.String],
                pt.abi.Uint32,
                pt.abi.StaticArray[pt.abi.Bool, Literal[32]],
            ],
            pt.abi.Uint8,
        ],
        ["order", "idx"],
        {
            "order": pt.abi.make(
                pt.abi.Tuple3[
                    pt.abi.DynamicArray[pt.abi.String],
                    pt.abi.Uint32,
                    pt.abi.StaticArray[pt.abi.Bool, Literal[32]],
                ]
            ).type_spec(),
            "idx": pt.abi.Uint8().type_spec(),
        },
        "((string[],uint32,bool[32]),uint8)",
    ),
]


@pytest.mark.parametrize(
    "model, annotation_type, field_names, type_specs, strified", MODEL_TESTS
)
def test_model_create(model: Model, annotation_type, field_names, type_specs, strified):

    assert model.annotation_type() == annotation_type
    assert model.field_names == field_names
    assert model.type_specs == type_specs
    assert model.__str__() == strified
    assert model.type_spec() == pt.abi.type_spec_from_annotation(annotation_type)