from Orange.data import ContinuousVariable, Domain, StringVariable

from .base import *
import pandas as pd
from pandas.sparse.array import BlockIndex


class Table(TableBase, pd.DataFrame):
    KNOWN_PANDAS_KWARGS = {"data", "index", "columns", "dtype", "copy"}

    @property
    def _constructor(self):
        """Proper pandas extension as per http://pandas.pydata.org/pandas-docs/stable/internals.html"""
        return Table

    @property
    def _constructor_sliced(self):
        """
        An ugly workaround for the fact that pandas doesn't transfer _metadata to Series objects.
        Where this property should return a constructor callable, we instead return a
        proxy function, which sets the necessary properties from _metadata using a closure
        to ensure thread-safety.

        This enables TableSeries to use .X/.Y/.metas because it has a Domain.
        """
        attrs = {k: getattr(self, k, None) for k in Table._metadata}

        class _transferer:
            # this is a class and not a function because sometimes, pandas
            # wants _constructor_sliced.from_array
            def from_array(self, *args, **kwargs):
                return _transferer._attr_setter(TableSeries.from_array(*args, **kwargs))

            def __call__(self, *args, **kwargs):
                return _transferer._attr_setter(TableSeries(*args, **kwargs))

            @staticmethod
            def _attr_setter(target):
                for k, v in attrs.items():
                    setattr(target, k, v)
                return target

        return _transferer()

    @property
    def _constructor_expanddim(self):
        return TablePanel

    @property
    def density(self):
        """
        Compute the table density.
        Return the ratio of null values (pandas interpretation of null)
        """
        return 1 - self.isnull().sum().sum() / self.size

    def X_density(self):
        return TableBase.DENSE

    def Y_density(self):
        return TableBase.DENSE

    def metas_density(self):
        return TableBase.DENSE

    @property
    def is_sparse(self):
        return False


class TableSeries(SeriesBase, pd.Series):
    @property
    def _constructor(self):
        return TableSeries

    @property
    def _constructor_expanddim(self):
        return Table


class TablePanel(PanelBase, pd.Panel):
    @property
    def _constructor(self):
        return TablePanel

    @property
    def _constructor_sliced(self):
        return Table


class SparseTable(TableBase, pd.SparseDataFrame):
    # this differs from Table.KNOWN_PANDAS_KWARGS by default_kind and default_fill_value
    KNOWN_PANDAS_KWARGS = {"data", "index", "columns", "dtype", "copy", "default_kind", "default_fill_value"}

    @property
    def _constructor(self):
        """Proper pandas extension as per http://pandas.pydata.org/pandas-docs/stable/internals.html"""
        return SparseTable

    @property
    def _constructor_sliced(self):
        """
        An ugly workaround for the fact that pandas doesn't transfer _metadata to Series objects.
        Where this property should return a constructor callable, we instead return a
        proxy function, which sets the necessary properties from _metadata using a closure
        to ensure thread-safety.

        This enables TableSeries to use .X/.Y/.metas because it has a Domain.
        """
        attrs = {k: getattr(self, k, None) for k in Table._metadata}

        class _transferer:
            # this is a class and not a function because sometimes, pandas
            # wants _constructor_sliced.from_array
            def from_array(self, *args, **kwargs):
                return _transferer._attr_setter(SparseTableSeries.from_array(*args, **kwargs))

            def __call__(self, *args, **kwargs):
                return _transferer._attr_setter(SparseTableSeries(*args, **kwargs))

            @staticmethod
            def _attr_setter(target):
                for k, v in attrs.items():
                    setattr(target, k, v)
                return target

        return _transferer()

    @property
    def _constructor_expanddim(self):
        return SparseTablePanel

    def __setitem__(self, key, value):
        # we don't want any special handling, use pandas directly
        return pd.SparseDataFrame.__setitem__(self, key, value)

    def _to_numpy(self, X=False, Y=False, meta=False, writable=False):
        """
        Unlike the default _to_numpy, this creates scipy.sparse matrices.
        Does not generate a dense matrix in memory.
        Returns scipy.sparse.coo_matrix.
        """
        cols = []
        cols += self.domain.attributes if X else []
        cols += self.domain.class_vars if Y else []
        cols += self.domain.metas if meta else []
        n_rows = 1 if isinstance(self, SeriesBase) else len(self)

        # return empty if no columns: concatenation below needs some data
        # and in this case, there is none
        if not cols:
            return sp.coo_matrix((len(self), 0), dtype=np.float64)

        # adapted from https://stackoverflow.com/a/37417084
        #  - does not handle dense columns (we have none)
        # in a nutshell, gets the coo_matrix building components directly
        # from each column of the SparseTable
        result_data = []
        result_row = []
        result_col = []
        for i, col in enumerate(cols):
            column_index = self[col.name].sp_index
            if isinstance(column_index, BlockIndex):
                column_index = column_index.to_int_index()
            result_data.append(self[col.name].sp_values)
            result_row.append(column_index.indices)
            result_col.append(len(self[col.name].sp_values) * [i])
        return sp.coo_matrix((np.concatenate(result_data), (np.concatenate(result_row), np.concatenate(result_col))),
                             (n_rows, len(cols)), dtype=np.float64)

    @property
    def Y(self):
        # subscripting sparse matrices doesn't work, so get a copy
        result = self._to_numpy(Y=True)
        return result.getcol(0).tocoo() if result.shape[1] == 1 else result

    @classmethod
    def _coo_to_sparse_dataframe(cls, coo_matrix, column_index_start):
        """
        Convert a scipy.sparse.coo_matrix into a sparse dataframe,
        with indices and columns starting from 0.

        This constructs a single SparseTableSeries, which is then used to fill up
        the resulting SparseTable column-by-column. This is, counter-intuitively,
        a good way of doing things.

        We can't create a SparseDataFrame from a SparseSeries and then unstack
        the MultiIndex, because that gives us a dense DataFrame.

        We can't pass a list of SparseSeries rows to the SparseDataFrame constructor,
        as we would with a dense DataFrame, because that doesn't (yet?) work.
        """
        # convert into a multiindex sparse series
        # transposed because it's easier to get rows from ss
        # use a dense index so this works when a row is all-nan
        ss = pd.SparseSeries.from_coo(coo_matrix.T, dense_index=True)

        # create a new, completely empty sparse container
        # and fill its columns up sequentially
        # use a SparseDataFrame so we don't do any weights
        result = pd.SparseDataFrame(index=list(range(coo_matrix.shape[0])),
                                    columns=list(range(column_index_start, column_index_start + coo_matrix.shape[1])))
        for data_column_index, result_column_label in zip(range(coo_matrix.shape[1]), result.columns):
            if coo_matrix.shape[1] == 1:
                # an SS generated from a column vector is different
                col = ss
            else:
                # use only the first level index (we have two)
                col = ss.loc[data_column_index, :]
            # rewrite index from tuples of (selected_level, col) into just (col)
            # because selected_level is the same (we've selected it)
            col.index = [i[1] for i in col.index]
            result[result_column_label] = col
        return result

    @classmethod
    def _from_sparse_numpy(cls, domain, X, Y=None, metas=None, weights=None):
        """
        Construct a SparseTable from scipy.sparse matrices.
        This accepts X/Y/metas-like matrices (as in no strings) because
        scipy.sparse doesn't support anything other than numbers.
        """
        if domain is None:
            # legendary inference: everything is continuous! :D
            domain = Domain(
                [ContinuousVariable("Feature " + str(i)) for i in list(range(X.shape[1] if X is not None else 0))],
                [ContinuousVariable("Target " + str(i)) for i in list(range(Y.shape[1] if Y is not None else 0))],
                [ContinuousVariable("Meta " + str(i)) for i in list(range(metas.shape[1] if metas is not None else 0))]
            )

        # convert everything to coo because that's what pandas works with currently (0.18.1)
        # converting csc and csr to coo has linear complexity (per the scipy docs)
        def _any_to_coo(mat):
            if mat is None or sp.isspmatrix_coo(mat):
                return mat
            elif not sp.issparse(mat):
                return sp.coo_matrix(mat)
            else:
                return mat.tocoo()
        X = _any_to_coo(X)
        Y = _any_to_coo(Y)
        metas = _any_to_coo(metas)
        weights = _any_to_coo(weights)

        # our Y needs to be 2D (problem with 1-column .Y)
        if Y is not None and len(Y.shape) != 2:
            raise ValueError("Expected Y to be two-dimensional.")

        # sparse structures can't hold anything other than continuous variables, so limit
        # the domain (also: isinstance(TimeVariable(), ContinuousVariable) == True)
        columns = []
        for v in domain.attributes + domain.class_vars + domain.metas or []:
            if isinstance(v, StringVariable):
                raise ValueError("Sparse matrices do not support string variables.")
            columns.append(v.name)

        partial_sdfs = []
        col_idx_start = 0
        for role_array in (X, Y, metas):
            if role_array is None:
                continue
            # unstack to convert the 2-level index (one for each coordinate dimension)
            # into 2 indexes - rows and columns
            partial_sdfs.append(cls._coo_to_sparse_dataframe(role_array, col_idx_start))
            col_idx_start += role_array.shape[1]
        # instruct pandas not to copy unnecessarily
        # and coerce SparseDataFrame into SparseTable
        result = cls(data=pd.concat(partial_sdfs, axis=1, copy=False))
        # rename the columns from column indices to proper names
        # and the rows into globally unique labels
        result.columns = columns + [cls._WEIGHTS_COLUMN]
        result.index = cls._new_id(len(result), force_list=True)
        result.domain = domain
        result.set_weights(weights or 1)  # weights can be None
        return result

    @property
    def density(self):
        """
        Compute the table density.
        Return the density as reported by pd.SparseDataFrame
        """
        return pd.SparseDataFrame.density(self)

    def X_density(self):
        return TableBase.SPARSE

    def Y_density(self):
        return TableBase.SPARSE

    def metas_density(self):
        return TableBase.SPARSE

    @property
    def is_sparse(self):
        return True


class SparseTableSeries(SeriesBase, pd.SparseSeries):
    @property
    def _constructor(self):
        return SparseTableSeries

    @property
    def _constructor_expanddim(self):
        return SparseTable


class SparseTablePanel(PanelBase, pd.SparsePanel):
    @property
    def _constructor(self):
        return SparseTablePanel

    @property
    def _constructor_sliced(self):
        return SparseTable