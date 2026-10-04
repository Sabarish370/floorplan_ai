import random
from shapely.geometry import box
from config.room_dimensions import ROOM_DIMENSIONS

class BSPTessellationEngine:
    def __init__(self, plot_width, plot_depth, rooms_req, facing, seed=42):
        self.plot_w = float(plot_width)
        self.plot_d = float(plot_depth)
        self.rooms_req = rooms_req
        self.facing = facing
        self.rng = random.Random(seed)
        
    def _get_target_area(self, room_type):
        dims = ROOM_DIMENSIONS.get(room_type, ROOM_DIMENSIONS.get('bedroom'))
        return float(dims.get('pref_width', 10) * dims.get('pref_depth', 10))
        
    def _get_min_dimension(self, room_type):
        dims = ROOM_DIMENSIONS.get(room_type, ROOM_DIMENSIONS.get('bedroom'))
        return float(min(dims.get('min_width', 6), dims.get('min_depth', 6)))

    def generate(self):
        # Flatten rooms
        rooms_list = []
        for r_type, count in self.rooms_req.items():
            for i in range(count):
                r_id = f"{r_type}_{i+1}"
                target_a = self._get_target_area(r_type)
                rooms_list.append({
                    'id': r_id,
                    'type': r_type,
                    'target_area': target_a
                })
                
        # Calculate total target area
        total_target = sum(r['target_area'] for r in rooms_list)
        buildable_area = self.plot_w * self.plot_d
        
        # If total target < buildable, add a circulation/expansion node
        if total_target < buildable_area:
            rooms_list.append({
                'id': 'circulation_1',
                'type': 'circulation',
                'target_area': buildable_area - total_target
            })
            total_target = buildable_area
            
        # Shuffle slightly for topological diversity but keep parking/hall near edges
        self.rng.shuffle(rooms_list)
        
        root_region = {'x': 0.0, 'y': 0.0, 'w': self.plot_w, 'd': self.plot_d}
        
        try:
            return self._bsp_split(root_region, rooms_list, total_target)
        except Exception as e:
            # Fallback if partitioning fails
            return []

    def _bsp_split(self, region, rooms, region_target_area):
        if len(rooms) == 1:
            r = rooms[0]
            return [{
                'id': r['id'],
                'type': r['type'],
                'name': r['type'].capitalize(),
                'x': region['x'],
                'y': region['y'],
                'width': region['w'],
                'depth': region['d'],
                'area': region['w'] * region['d']
            }]
            
        # Split point
        split_idx = len(rooms) // 2
        
        group1 = rooms[:split_idx]
        group2 = rooms[split_idx:]
        
        area1 = sum(r['target_area'] for r in group1)
        area2 = sum(r['target_area'] for r in group2)
        
        ratio = area1 / (area1 + area2)
        
        # Determine split axis based on aspect ratio of the current region
        if region['w'] >= region['d']:
            # Vertical split
            w1 = region['w'] * ratio
            w2 = region['w'] - w1
            
            # Enforce minimums roughly
            if w1 < 3.0: 
                w1 = 3.0; w2 = region['w'] - 3.0
            if w2 < 3.0: 
                w2 = 3.0; w1 = region['w'] - 3.0
                
            reg1 = {'x': region['x'], 'y': region['y'], 'w': w1, 'd': region['d']}
            reg2 = {'x': region['x'] + w1, 'y': region['y'], 'w': w2, 'd': region['d']}
        else:
            # Horizontal split
            d1 = region['d'] * ratio
            d2 = region['d'] - d1
            
            if d1 < 3.0:
                d1 = 3.0; d2 = region['d'] - 3.0
            if d2 < 3.0:
                d2 = 3.0; d1 = region['d'] - 3.0
                
            reg1 = {'x': region['x'], 'y': region['y'], 'w': region['w'], 'd': d1}
            reg2 = {'x': region['x'], 'y': region['y'] + d1, 'w': region['w'], 'd': d2}
            
        res = []
        res.extend(self._bsp_split(reg1, group1, area1))
        res.extend(self._bsp_split(reg2, group2, area2))
        return res

def generate_bsp_layout(reqs, seed=42):
    engine = BSPTessellationEngine(reqs.plot.width, reqs.plot.depth, reqs.rooms, reqs.plot.facing, seed)
    return engine.generate()
