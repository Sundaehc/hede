import pytest

from domain.auth_schema import METADATA
from storage.auth_repository import AuthRepository


@pytest.fixture
def user_repository():
    repository = AuthRepository("sqlite://")
    METADATA.create_all(repository.engine)
    repository.seed_defaults()
    for username, name, department, status in (
        ("first", "张三", "商品部", "active"),
        ("second", "张小明", "开发部", "disabled"),
        ("张-account", "李四", "商品部", "active"),
        ("english", "Alice Chen", "开发部", "active"),
        ("percent", "姓名%测试", "商品部", "active"),
        ("underscore", "姓名_测试", "商品部", "active"),
    ):
        repository.create_user({
            "username": username,
            "password": "test-password",
            "display_name": name,
            "department_code": department,
            "role_code": "super_admin",
            "status": status,
        }, first_user_is_admin=False)
    try:
        yield repository
    finally:
        repository.engine.dispose()


def test_name_filter_matches_partial_names_before_pagination(user_repository):
    first_page = user_repository.list_users_page(page=1, page_size=1, name_query=" 张 ")
    second_page = user_repository.list_users_page(page=2, page_size=1, name_query="张")

    assert [user["display_name"] for user in first_page["items"]] == ["张三"]
    assert [user["display_name"] for user in second_page["items"]] == ["张小明"]
    assert first_page["total"] == second_page["total"] == 2
    assert first_page["stats"] == second_page["stats"] == {
        "active": 1, "disabled": 1, "department_count": 2,
    }


@pytest.mark.parametrize("name_query", [None, "", "   "])
def test_blank_name_filter_returns_all_users(user_repository, name_query):
    result = user_repository.list_users_page(page=1, page_size=20, name_query=name_query)

    assert result["total"] == len(result["items"]) == 6
    assert result["stats"] == {"active": 5, "disabled": 1, "department_count": 2}


def test_name_filter_is_case_insensitive(user_repository):
    result = user_repository.list_users_page(page=1, page_size=20, name_query="alice")

    assert [user["display_name"] for user in result["items"]] == ["Alice Chen"]


@pytest.mark.parametrize("name_query,expected_name", [("%", "姓名%测试"), ("_", "姓名_测试")])
def test_name_filter_treats_sql_wildcards_as_literal_text(user_repository, name_query, expected_name):
    result = user_repository.list_users_page(page=1, page_size=20, name_query=name_query)

    assert result["total"] == 1
    assert result["items"][0]["display_name"] == expected_name


def test_unmatched_name_filter_returns_empty_results_and_stats(user_repository):
    result = user_repository.list_users_page(page=1, page_size=20, name_query="不存在")

    assert result["items"] == []
    assert result["total"] == 0
    assert result["stats"] == {"active": 0, "disabled": 0, "department_count": 0}
