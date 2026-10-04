from models.floorplan import FloorPlan

def render_svg(plot_width: float, plot_depth: float, facing: str, layout, pixels_per_ft: float = 15.0, show_vastu_grid: bool = False, vastu_data: dict = None) -> str:
    # Handle FloorPlan object instead of old signature if passed
    if hasattr(layout, 'rooms'):
        plan = layout
        plot_w = plan.plot_width
        plot_d = plan.plot_depth
        facing = plan.facing.lower()
        rooms = plan.rooms
        doors = plan.doors
        entrance = plan.entrance
        vehicle_gate = getattr(plan, 'vehicle_gate', None)
    else:
        # Fallback for unexpected usages, though we should always pass FloorPlan now
        plot_w = plot_width
        plot_d = plot_depth
        rooms = layout
        doors = []
        entrance = None
        vehicle_gate = None

    scale = pixels_per_ft
    svg_w = (plot_w + 10) * scale
    svg_h = (plot_d + 10) * scale
    
    offset_x = 5 * scale
    offset_y = 5 * scale
    
    svg = f'<svg width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg">\n'
    
    # Background
    svg += f'<rect width="100%" height="100%" fill="#f8f9fa" />\n'
    
    # Plot Boundary
    svg += f'<rect x="{offset_x}" y="{offset_y}" width="{plot_w * scale}" height="{plot_d * scale}" fill="none" stroke="#333" stroke-width="3" stroke-dasharray="5,5" />\n'
    
    # Draw rooms
    colors = {
        "bedroom": "#e3f2fd",
        "hall": "#fff3e0",
        "kitchen": "#e8f5e9",
        "bathroom": "#f3e5f5",
        "pooja": "#fff8e1",
        "parking": "#eeeeee",
        "dining": "#fbe9e7",
        "utility": "#eceff1",
        "circulation": "#f0f4c3",
    }
    
    for room in rooms:
        # Check if room is object or dict (for fallback)
        if isinstance(room, dict):
            rx, ry, rw, rh = room['x'], room['y'], room['width'], room['depth']
            rtype, rname = room['type'], room['name']
        else:
            rx, ry, rw, rh = room.x, room.y, room.width, room.depth
            rtype, rname = room.type, room.name
            
        rx_scaled = offset_x + rx * scale
        ry_scaled = offset_y + ry * scale
        rw_scaled = rw * scale
        rh_scaled = rh * scale
        
        color = colors.get(rtype, "#ffffff")
        
        svg += f'<rect x="{rx_scaled}" y="{ry_scaled}" width="{rw_scaled}" height="{rh_scaled}" fill="{color}" stroke="#333" stroke-width="2" />\n'
        
        # Room text
        cx = rx_scaled + rw_scaled / 2
        cy = ry_scaled + rh_scaled / 2
        # Automatically scale text a bit based on room size if needed, but a fixed 14/12 looks okay for standard sizes
        svg += f'<text x="{cx}" y="{cy - 5}" font-family="Arial" font-size="14" font-weight="bold" fill="#333" text-anchor="middle">{rname}</text>\n'
        svg += f'<text x="{cx}" y="{cy + 15}" font-family="Arial" font-size="12" fill="#666" text-anchor="middle">{rw} x {rh} ft</text>\n'
        
    # Draw doors
    for door in doors:
        dx = offset_x + door.x * scale
        dy = offset_y + door.y * scale
        dw = door.width * scale
        
        if door.wall_side == "horizontal":
            svg += f'<rect x="{dx}" y="{dy-3}" width="{dw}" height="6" fill="#fff" stroke="#ff9800" stroke-width="2" />\n'
            # svg += f'<text x="{dx+dw/2}" y="{dy-5}" font-family="Arial" font-size="10" fill="#ff9800" text-anchor="middle">Door</text>\n'
        else:
            svg += f'<rect x="{dx-3}" y="{dy}" width="6" height="{dw}" fill="#fff" stroke="#ff9800" stroke-width="2" />\n'
            # svg += f'<text x="{dx-5}" y="{dy+dw/2}" font-family="Arial" font-size="10" fill="#ff9800" text-anchor="middle" transform="rotate(-90 {dx-5},{dy+dw/2})">Door</text>\n'
            
    # Draw entrance
    if entrance:
        ent = entrance
        ex = offset_x + ent.x * scale
        ey = offset_y + ent.y * scale
        ew = ent.width * scale
        
        if ent.side in ['north', 'south']:
            svg += f'<rect x="{ex-ew/2}" y="{ey-5}" width="{ew}" height="10" fill="#4caf50" />\n'
            svg += f'<text x="{ex}" y="{ey-10 if ent.side=="north" else ey+20}" font-family="Arial" font-size="12" font-weight="bold" fill="#4caf50" text-anchor="middle">MAIN ENTRANCE</text>\n'
        else:
            svg += f'<rect x="{ex-5}" y="{ey-ew/2}" width="10" height="{ew}" fill="#4caf50" />\n'
            svg += f'<text x="{ex-10 if ent.side=="west" else ex+10}" y="{ey}" font-family="Arial" font-size="12" font-weight="bold" fill="#4caf50" text-anchor="middle" transform="rotate(-90 {ex-10 if ent.side=="west" else ex+10},{ey})">MAIN ENTRANCE</text>\n'
            
    # Draw vehicle gate
    if vehicle_gate:
        vg = vehicle_gate
        vx = offset_x + vg.x * scale
        vy = offset_y + vg.y * scale
        vw = vg.width * scale
        
        if vg.side in ['north', 'south']:
            svg += f'<rect x="{vx-vw/2}" y="{vy-5}" width="{vw}" height="10" fill="#2196f3" />\n'
            svg += f'<text x="{vx}" y="{vy-10 if vg.side=="north" else vy+20}" font-family="Arial" font-size="12" font-weight="bold" fill="#2196f3" text-anchor="middle">VEHICLE GATE</text>\n'
        else:
            svg += f'<rect x="{vx-5}" y="{vy-vw/2}" width="10" height="{vw}" fill="#2196f3" />\n'
            svg += f'<text x="{vx-10 if vg.side=="west" else vx+10}" y="{vy}" font-family="Arial" font-size="12" font-weight="bold" fill="#2196f3" text-anchor="middle" transform="rotate(-90 {vx-10 if vg.side=="west" else vx+10},{vy})">VEHICLE GATE</text>\n'
            
    # Draw road
    if facing == 'east':
        rx = offset_x + plot_w * scale + 40
        ry = offset_y + (plot_d * scale) / 2
        svg += f'<text x="{rx}" y="{ry}" font-family="Arial" font-size="16" font-weight="bold" fill="#757575" text-anchor="middle" transform="rotate(-90 {rx},{ry})">ROAD (EAST FACING) →→→</text>\n'
    elif facing == 'west':
        rx = offset_x - 40
        ry = offset_y + (plot_d * scale) / 2
        svg += f'<text x="{rx}" y="{ry}" font-family="Arial" font-size="16" font-weight="bold" fill="#757575" text-anchor="middle" transform="rotate(-90 {rx},{ry})">←←← ROAD (WEST FACING)</text>\n'
    elif facing == 'north':
        rx = offset_x + (plot_w * scale) / 2
        ry = offset_y - 40
        svg += f'<text x="{rx}" y="{ry}" font-family="Arial" font-size="16" font-weight="bold" fill="#757575" text-anchor="middle">ROAD (NORTH FACING) ↑↑↑</text>\n'
    elif facing == 'south':
        rx = offset_x + (plot_w * scale) / 2
        ry = offset_y + plot_d * scale + 40
        svg += f'<text x="{rx}" y="{ry}" font-family="Arial" font-size="16" font-weight="bold" fill="#757575" text-anchor="middle">↓↓↓ ROAD (SOUTH FACING)</text>\n'
        
    # Draw Vastu Grid if requested
    if show_vastu_grid:
        # Draw 3x3 grid
        w3 = (plot_w * scale) / 3
        d3 = (plot_d * scale) / 3
        
        for i in range(1, 3):
            vx = offset_x + i * w3
            svg += f'<line x1="{vx}" y1="{offset_y}" x2="{vx}" y2="{offset_y + plot_d * scale}" stroke="#9c27b0" stroke-width="2" stroke-dasharray="10,5" opacity="0.6"/>\n'
            
            vy = offset_y + i * d3
            svg += f'<line x1="{offset_x}" y1="{vy}" x2="{offset_x + plot_w * scale}" y2="{vy}" stroke="#9c27b0" stroke-width="2" stroke-dasharray="10,5" opacity="0.6"/>\n'
            
        # Draw zone labels roughly in centers
        zones = [
            ("NW", 0.5, 0.5), ("N", 1.5, 0.5), ("NE", 2.5, 0.5),
            ("W", 0.5, 1.5), ("CENTER", 1.5, 1.5), ("E", 2.5, 1.5),
            ("SW", 0.5, 2.5), ("S", 1.5, 2.5), ("SE", 2.5, 2.5)
        ]
        
        for z, i, j in zones:
            zx = offset_x + i * w3
            zy = offset_y + j * d3
            svg += f'<text x="{zx}" y="{zy}" font-family="Arial" font-size="24" font-weight="bold" fill="#9c27b0" opacity="0.3" text-anchor="middle">{z}</text>\n'
            
        # Draw room centroids
        if vastu_data and 'room_zones' in vastu_data:
            for r_id, r_info in vastu_data['room_zones'].items():
                cx = offset_x + r_info['center']['x'] * scale
                cy = offset_y + r_info['center']['y'] * scale
                r_zone = r_info['zone']
                
                svg += f'<circle cx="{cx}" cy="{cy}" r="5" fill="#e91e63" />\n'
                svg += f'<text x="{cx+8}" y="{cy+4}" font-family="Arial" font-size="12" font-weight="bold" fill="#e91e63">{r_zone}</text>\n'
                
    svg += '</svg>'
    return svg
