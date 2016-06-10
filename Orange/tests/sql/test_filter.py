# Test methods with long descriptive names can omit docstrings
# pylint: disable=missing-docstring

import unittest

import numpy as np
import pandas as pd

from Orange.data.sql.table import SqlTable
from Orange.data import domain
from Orange.tests.sql.base import PostgresTest, sql_version, sql_test
import Orange.data.sql.compat.filter as filter

@sql_test
class TestIsDefinedSql(PostgresTest):
    def setUp(self):
        self.data = [
            [1, 2, 3, np.nan, 'm'],
            [2, 3, 1, 4, 'f'],
            [np.nan, np.nan, np.nan, np.nan, np.nan],
            [7, np.nan, 3, np.nan, 'f'],
        ]
        conn, self.table_name = self.create_sql_table(self.data)
        table = SqlTable(conn, self.table_name, inspect_values=True)
        variables = table.domain.variables
        new_table = table.copy()
        new_table.domain = domain.Domain(variables[:-1], variables[-1:])
        self.table = new_table

    def tearDown(self):
        self.drop_sql_table(self.table_name)

    def test_on_all_columns(self):
        filtered_data = filter.IsDefined()(self.table)
        correct_data = [row for row in self.data if all(not pd.isnull(e) for e in row)]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-1] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [self.table.domain.class_var.to_val(r[-1]) for r in correct_data])

    def test_selected_columns(self):
        filtered_data = filter.IsDefined(columns=[0])(self.table)
        correct_data = [row for row in self.data if not pd.isnull(row[0])]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-1] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [self.table.domain.class_var.to_val(r[-1]) for r in correct_data])

    def test_all_columns_negated(self):
        filtered_data = filter.IsDefined(negate=True)(self.table)
        correct_data = [row for row in self.data if not all(not pd.isnull(e) for e in row)]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-1] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [self.table.domain.class_var.to_val(r[-1]) for r in correct_data])

    def test_selected_columns_negated(self):
        filtered_data = filter.IsDefined(negate=True, columns=[4])(self.table)
        correct_data = [row for row in self.data if pd.isnull(row[4])]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-1] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [self.table.domain.class_var.to_val(r[-1]) for r in correct_data])

    def test_can_inherit_is_defined_filter(self):
        filtered_data = filter.IsDefined(columns=[1])(self.table)
        filtered_data = filtered_data[:, 4]
        correct_data = [[row[4]] for row in self.data if not pd.isnull(row[1])]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-1] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [self.table.domain.class_var.to_val(r[-1]) for r in correct_data])


@sql_test
class TestHasClass(PostgresTest):
    def setUp(self):
        self.data = [
            [1, 2, 3, np.nan, 'm'],
            [2, 3, 1, 4, 'f'],
            [5, np.nan, np.nan, np.nan, np.nan],
            [7, np.nan, 3, np.nan, 'f'],
        ]

        self.conn, self.table_name = self.create_sql_table(self.data)
        table = SqlTable(self.conn, self.table_name, inspect_values=True)
        variables = table.domain.variables
        new_table = table.copy()
        new_table.domain = domain.Domain(variables[:-1], variables[-1:])
        self.table = new_table

    def tearDown(self):
        self.drop_sql_table(self.table_name)

    def test_has_class(self):
        filtered_data = filter.HasClass()(self.table)
        correct_data = [r for r in self.data if not pd.isnull(r[-1])]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-1] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [self.table.domain.class_var.to_val(r[-1]) for r in correct_data])

    def test_negated(self):
        filtered_data = filter.HasClass(negate=True)(self.table)
        correct_data = [r for r in self.data if pd.isnull(r[-1])]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.X, [r[:-1] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [r[-1] for r in correct_data])


@sql_test
class TestSameValueSql(PostgresTest):
    def setUp(self):
        self.data = [
            [1, 2, 3, 'a', 'm'],
            [2, np.nan, 1, 'a', 'f'],
            [np.nan, 3, 1, 'b', np.nan],
            [2, 2, 3, 'b', 'f'],
        ]
        self.conn, self.table_name = self.create_sql_table(self.data)
        table = SqlTable(self.conn, self.table_name, inspect_values=True)
        variables = table.domain.variables
        new_table = table.copy()
        new_table.domain = domain.Domain(variables[:-2], variables[-2:])
        self.table = new_table

    def tearDown(self):
        self.drop_sql_table(self.table_name)

    def test_on_continuous_attribute(self):
        filtered_data = filter.SameValue(0, 1)(self.table)
        correct_data = [row for row in self.data if row[0] == 1]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_on_continuous_attribute_with_unknowns(self):
        filtered_data = filter.SameValue(1, 2)(self.table)
        correct_data = [row for row in self.data if row[1] == 2]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_on_continuous_attribute_with_unknown_value(self):
        filtered_data = filter.SameValue(1, None)(self.table)
        correct_data = [row for row in self.data if pd.isnull(row[1])]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_on_continuous_attribute_negated(self):
        filtered_data = filter.SameValue(0, 1, negate=True)(self.table)
        correct_data = [row for row in self.data if not row[0] == 1]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_on_discrete_attribute(self):
        filtered_data = filter.SameValue(3, 'a')(self.table)
        correct_data = [row for row in self.data if row[3] == 'a']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_on_discrete_attribute_with_unknown_value(self):
        filtered_data = filter.SameValue(4, None)(self.table)
        correct_data = [row for row in self.data if pd.isnull(row[4])]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_on_discrete_attribute_with_unknowns(self):
        filtered_data = filter.SameValue(4, 'm')(self.table)
        correct_data = [row for row in self.data if row[4] == 'm']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_on_discrete_attribute_negated(self):
        filtered_data = filter.SameValue(3, 'a', negate=True)(self.table)
        correct_data = [row for row in self.data if not row[3] == 'a']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])


@sql_test
class TestValuesSql(PostgresTest):
    def setUp(self):
        self.data = [
            [1, 2, 3, 'a', 'm'],
            [2, np.nan, 1, 'a', 'f'],
            [np.nan, 3, 1, 'b', np.nan],
            [2, 2, 3, 'b', 'f'],
        ]
        conn, self.table_name = self.create_sql_table(self.data)
        table = SqlTable(conn, self.table_name, inspect_values=True)
        variables = table.domain.variables
        new_table = table.copy()
        new_table.domain = domain.Domain(variables[:-2], variables[-2:])
        self.table = new_table

    def tearDown(self):
        self.drop_sql_table(self.table_name)

    def test_values_filter_with_no_conditions(self):
        with self.assertRaises(ValueError):
            filtered_data = filter.Values([])(self.table)

    def test_discrete_value_filter(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterDiscrete(3, ['a'])
        ])(self.table)
        correct_data = [row for row in self.data if row[3] in ['a']]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_discrete_value_filter_with_multiple_values(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterDiscrete(3, ['a', 'b'])
        ])(self.table)
        correct_data = [row for row in self.data if row[3] in ['a', 'b']]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_discrete_value_filter_with_None(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterDiscrete(3, None)
        ])(self.table)
        correct_data = [row for row in self.data if not pd.isnull(row[3])]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_continuous_value_filter_equal(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterContinuous(0, filter.FilterContinuous.Equal, 1)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] == 1]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_continuous_value_filter_not_equal(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterContinuous(0, filter.FilterContinuous.NotEqual, 1)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] != 1]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_continuous_value_filter_less(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterContinuous(0, filter.FilterContinuous.Less, 2)
        ])(self.table)
        correct_data = [row for row in self.data if not pd.isnull(row[0]) and row[0] < 2]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_continuous_value_filter_less_equal(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterContinuous(0, filter.FilterContinuous.LessEqual, 2)
        ])(self.table)
        correct_data = [row for row in self.data if not pd.isnull(row[0]) and row[0] <= 2]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_continuous_value_filter_greater(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterContinuous(0, filter.FilterContinuous.Greater, 1)
        ])(self.table)
        correct_data = [row for row in self.data if not pd.isnull(row[0]) and row[0] > 1]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_continuous_value_filter_greater_equal(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterContinuous(0, filter.FilterContinuous.GreaterEqual, 1)
        ])(self.table)
        correct_data = [row for row in self.data if not pd.isnull(row[0]) and row[0] >= 1]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_continuous_value_filter_between(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterContinuous(0, filter.FilterContinuous.Between, 1, 2)
        ])(self.table)
        correct_data = [row for row in self.data if not pd.isnull(row[0]) and 1 <= row[0] <= 2]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_continuous_value_filter_outside(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterContinuous(0, filter.FilterContinuous.Outside, 2, 3)
        ])(self.table)
        correct_data = [row for row in self.data if not pd.isnull(row[0]) and not 2 <= row[0] <= 3]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])

    def test_continuous_value_filter_isdefined(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterContinuous(1, filter.FilterContinuous.IsDefined)
        ])(self.table)
        correct_data = [row for row in self.data if not pd.isnull(row[1])]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        assert_seq_equal_with_nans(filtered_data.X, [r[:-2] for r in correct_data])
        np.testing.assert_equal(filtered_data.Y, [[self.table.domain.class_vars[0].to_val(r[-2]),
                                                   self.table.domain.class_vars[1].to_val(r[-1])]
                                                  for r in correct_data])


@sql_test
class TestFilterStringSql(PostgresTest):
    def setUp(self):
        self.data = [
            [w] for w in "Lorem ipsum dolor sit amet, consectetur adipiscing"
            "elit. Vestibulum vel dolor nulla. Etiam elit lectus, mollis nec"
            "mattis sed, pellentesque in turpis. Vivamus non nisi dolor. Etiam"
            "lacinia dictum purus, in ullamcorper ante vulputate sed. Nullam"
            "congue blandit elementum. Donec blandit laoreet posuere. Proin"
            "quis augue eget tortor posuere mollis. Fusce vestibulum bibendum"
            "neque at convallis. Donec iaculis risus volutpat malesuada"
            "vehicula. Ut cursus tempor massa vulputate lacinia. Pellentesque"
            "eu tortor sed diam placerat porttitor et volutpat risus. In"
            "vulputate rutrum lacus ac sagittis. Suspendisse interdum luctus"
            "sem auctor commodo.".split(' ')] + [[None], [None]]
        self.conn, self.table_name = self.create_sql_table(self.data)
        self.table = SqlTable(self.conn, self.table_name)

    def tearDown(self):
        self.drop_sql_table(self.table_name)

    def test_filter_string_is_defined(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.IsDefined)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_equal(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Equal, 'in')
        ])(self.table)
        correct_data = [row for row in self.data if row[0] == 'in']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_equal_case_insensitive_value(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Equal, 'In',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] == 'in']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_equal_case_insensitive_data(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Equal, 'donec',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] == 'Donec']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_not_equal(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.NotEqual, 'in')
        ])(self.table)
        correct_data = [row for row in self.data if row[0] != 'in']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas[:-2], correct_data[:-2])
        np.testing.assert_equal(filtered_data.metas[-2:], [[""], [""]])

    def test_filter_string_not_equal_case_insensitive_value(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.NotEqual, 'In',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] != 'in']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas[:-2], correct_data[:-2])
        np.testing.assert_equal(filtered_data.metas[-2:], [[""], [""]])

    def test_filter_string_not_equal_case_insensitive_data(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.NotEqual, 'donec',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] != 'Donec']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas[:-2], correct_data[:-2])
        np.testing.assert_equal(filtered_data.metas[-2:], [[""], [""]])

    def test_filter_string_less(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Less, 'A')
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0] < 'A']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        self.assertEqual(filtered_data.exact_len(), 0)

    def test_filter_string_less_case_insensitive_value(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Less, 'In',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0].lower() < 'in']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_less_case_insensitive_data(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Less, 'donec',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0].lower() < 'donec']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_less_equal(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.LessEqual, 'A')
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0] <= 'A']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        self.assertEqual(filtered_data.exact_len(), 0)

    def test_filter_string_less_equal_case_insensitive_value(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.LessEqual, 'In',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0].lower() <= 'in']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_less_equal_case_insensitive_data(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.LessEqual, 'donec',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0].lower() <= 'donec']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_greater(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Greater, 'volutpat')
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0] > 'volutpat']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_greater_case_insensitive_value(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Greater, 'In',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0].lower() > 'in']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_greater_case_insensitive_data(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Greater, 'donec',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0].lower() > 'donec']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_greater_equal(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.GreaterEqual, 'volutpat')
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0] >= 'volutpat']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_greater_equal_case_insensitive_value(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.GreaterEqual, 'In',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0].lower() >= 'in']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_greater_equal_case_insensitive_data(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.GreaterEqual, 'donec',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and row[0].lower() >= 'donec']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_between(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Between, 'a', 'c')
        ])(self.table)
        cols = filtered_data.columns
        x = filtered_data.metas
        correct_data = [row for row in self.data if row[0] is not None and 'a' <= row[0] <= 'c']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_between_case_insensitive_value(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Between, 'I', 'O',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and 'i' < row[0].lower() <= 'o']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_between_case_insensitive_data(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Between, 'i', 'O',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and 'i' <= row[0].lower() <= 'o']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_contains(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Contains, 'et')
        ])(self.table)
        correct_data = [row
                        for row in self.data
                        if row[0] is not None and 'et' in row[0]]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_contains_case_insensitive_value(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Contains, 'eT',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and 'et' in row[0].lower()]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_contains_case_insensitive_data(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Contains, 'do',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and 'do' in row[0].lower()]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_outside(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Outside, 'am', 'di')
        ])(self.table)
        correct_data = [row for row in self.data if row[0] is not None and not 'am' < row[0] < 'di']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_outside_case_insensitive(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.Outside, 'd', 'k',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row
                        for row in self.data
                        if row[0] is not None and not 'd' < row[0].lower() < 'k']

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_starts_with(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.StartsWith, 'D')
        ])(self.table)
        correct_data = [row
                        for row in self.data
                        if row[0] is not None and row[0].startswith('D')]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_starts_with_case_insensitive(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.StartsWith, 'D',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row
                        for row in self.data
                        if row[0] is not None
                        and row[0].lower().startswith('d')]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_ends_with(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.EndsWith, 's')
        ])(self.table)
        correct_data = [row
                        for row in self.data
                        if row[0] is not None and row[0].endswith('s')]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_ends_with_case_insensitive(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterString(-1, filter.FilterString.EndsWith, 'S',
                                case_sensitive=False)
        ])(self.table)
        correct_data = [row
                        for row in self.data
                        if row[0] is not None
                        and row[0].lower().endswith('s')]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_list(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterStringList(-1, ['et', 'in'])
        ])(self.table)
        correct_data = [row
                        for row in self.data if row[0] in ['et', 'in']]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_list_case_insensitive_value(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterStringList(-1, ['Et', 'In'], case_sensitive=False)
        ])(self.table)
        correct_data = [row
                        for row in self.data if row[0] in ['et', 'in']]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)

    def test_filter_string_list_case_insensitive_data(self):
        filtered_data = filter.Values(conditions=[
            filter.FilterStringList(-1, ['donec'], case_sensitive=False)
        ])(self.table)
        correct_data = [row
                        for row in self.data if row[0] in ['Donec']]

        self.assertEqual(filtered_data.exact_len(), len(correct_data))
        np.testing.assert_equal(filtered_data.metas, correct_data)


def assert_seq_equal_with_nans(seq1, seq2):
    try:
        np.testing.assert_equal(len(seq1), len(seq2))
        for row1, row2 in zip(seq1, seq2):
            np.testing.assert_equal(len(row1), len(row2))
            for val1, val2 in zip(row1, row2):
                np.testing.assert_equal(val1, val2)
    except AssertionError:
        import sys
        print(seq1, file=sys.stderr)
        print(seq2, file=sys.stderr)
        raise
