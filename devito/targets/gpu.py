import cgen as c

from devito.data import FULL
from devito.ir.iet import (Expression, Iteration, List, FindNodes, MapNodes,
                           Transformer, COLLAPSED, VECTOR, retrieve_iteration_tree)
from devito.targets.basic import Target
from devito.targets.common import (DataManager, Ompizer, ParallelTree, target_pass,
                                   optimize_halospots, mpiize, hoist_prodders)
from devito.tools import filter_sorted, flatten

__all__ = ['DeviceOffloadingTarget']


class OffloadingOmpizer(Ompizer):

    COLLAPSE_NCORES = 1
    """
    Always collapse when possible.
    """

    COLLAPSE_WORK = 1
    """
    Always collapse when possible.
    """

    lang = dict(Ompizer.lang)
    lang.update({
        'par-for-teams': lambda i:
            c.Pragma('omp target teams distribute parallel for collapse(%d)' % i),
        'map-enter-to': lambda i, j:
            c.Pragma('omp target enter data map(to: %s%s)' % (i, j)),
        'map-enter-alloc': lambda i, j:
            c.Pragma('omp target enter data map(alloc: %s%s)' % (i, j)),
        'map-exit-from': lambda i, j:
            c.Pragma('omp target exit data map(from: %s%s)' % (i, j)),
        'map-exit-delete': lambda i, j:
            c.Pragma('omp target exit data map(delete: %s%s)' % (i, j)),
    })

    def __init__(self, key=None):
        if key is None:
            key = lambda i: i.is_ParallelRelaxed
        super(OffloadingOmpizer, self).__init__(key=key)

    @classmethod
    def _map_data(cls, f):
        if f.is_Array:
            return f.symbolic_shape
        else:
            return tuple(f._C_get_field(FULL, d).size for d in f.dimensions)

    @classmethod
    def _map_to(cls, f):
        return cls.lang['map-enter-to'](f.name, ''.join('[0:%s]' % i
                                                        for i in cls._map_data(f)))

    @classmethod
    def _map_alloc(cls, f):
        return cls.lang['map-enter-alloc'](f.name, ''.join('[0:%s]' % i
                                                           for i in cls._map_data(f)))

    @classmethod
    def _map_from(cls, f):
        return cls.lang['map-exit-from'](f.name, ''.join('[0:%s]' % i
                                                         for i in cls._map_data(f)))

    @classmethod
    def _map_delete(cls, f):
        return cls.lang['map-exit-delete'](f.name, ''.join('[0:%s]' % i
                                                           for i in cls._map_data(f)))

    def _make_threaded_prodders(self, partree):
        # no-op for now
        return partree

    def _make_partree(self, candidates, nthreads=None):
        """
        Parallelize the `candidates` Iterations attaching suitable OpenMP pragmas
        for GPU offloading.
        """
        assert candidates
        root = candidates[0]

        # Get the collapsable Iterations
        collapsable = self._find_collapsable(root, candidates)
        ncollapse = 1 + len(collapsable)

        # Prepare to build a ParallelTree
        omp_pragma = self.lang['par-for-teams'](ncollapse)

        # Create a ParallelTree
        body = root._rebuild(pragmas=root.pragmas + (omp_pragma,),
                             properties=root.properties + (COLLAPSED(ncollapse),))
        partree = ParallelTree([], body, nthreads=nthreads)

        collapsed = [partree] + collapsable

        return root, partree, collapsed

    def _make_parregion(self, partree):
        # no-op for now
        return partree

    def _make_guard(self, partree, *args):
        # no-op for now
        return partree

    def _make_nested_partree(self, partree):
        # no-op for now
        return partree

    @target_pass
    def make_simd(self, iet, **kwargs):
        # No SIMD-ization for devices. We then drop the VECTOR property
        # so that later passes can perform more aggressive transformations
        mapper = {}
        for i in FindNodes(Iteration).visit(iet):
            if i.is_Vectorizable:
                properties = [p for p in i.properties if p is not VECTOR]
                mapper[i] = i._rebuild(properties=properties)

        iet = Transformer(mapper).visit(iet)

        return iet, {}


class OffloadingDataManager(DataManager):

    def _alloc_array_on_high_bw_mem(self, obj, storage):
        if obj in storage._high_bw_mem:
            return

        decl = c.Comment("no-op")
        alloc = OffloadingOmpizer._map_alloc(obj)
        free = OffloadingOmpizer._map_delete(obj)

        storage._high_bw_mem[obj] = (decl, alloc, free)

    def _map_function_on_high_bw_mem(self, obj, storage):
        if obj in storage._high_bw_mem:
            return

        decl = c.Comment("no-op")
        alloc = OffloadingOmpizer._map_to(obj)
        free = OffloadingOmpizer._map_from(obj)

        storage._high_bw_mem[obj] = (decl, alloc, free)


class DeviceOffloadingTarget(Target):

    def __init__(self, params, platform):
        super(DeviceOffloadingTarget, self).__init__(params, platform)

        # Shared-memory parallelizer
        self.ompizer = OffloadingOmpizer()

        # Data manager (declarations, definitions, movemented between
        # host and device, ...)
        self.data_manager = OffloadingDataManager()

    def _pipeline(self, graph):
        # Optimization and parallelism
        optimize_halospots(graph)
        if self.params['mpi']:
            mpiize(graph, mode=self.params['mpi'])
        self.ompizer.make_simd(graph, simd_reg_size=self.platform.simd_reg_size)
        if self.params['openmp']:
            self.ompizer.make_parallel(graph)
        hoist_prodders(graph)

        # Symbol definitions
        self.data_manager.place_definitions(graph)
        self.data_manager.place_casts(graph)
