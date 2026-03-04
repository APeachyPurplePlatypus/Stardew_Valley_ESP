# Stardew Valley ESP - Initial Commit

## Summary

This is the initial commit containing Stardew Valley save game data and analysis tools.

## What's Included

### Save Game Files
- **Tolkien_432258440/** - Main farm save directory
  - `SaveGameInfo` - Character profile and current status (23 KB)
  - `SaveGameInfo_old` - Previous day backup (16 KB)  
  - `Tolkien_432258440` - Full world state and farm data (2.6 MB)
  - `Tolkien_432258440_old` - Previous day world backup (3 MB)

### Analysis Tools
- **parse_save.py** - XML parser that extracts all save attributes to Excel
- **Stardew_Save_Attributes.xlsx** - Generated Excel file with 789 attributes from save data

### Configuration
- **.gitignore** - Python and IDE exclusions

## Current Game Status

| Attribute | Value |
|-----------|-------|
| **Farmer Name** | Tolkien (Male) |
| **Farm Name** | Tolkien |
| **Progress** | Day 2, Spring, Year 1 |
| **Money** | 500g |
| **Health/Stamina** | 100/270 |
| **All Skills** | Level 0 (Just started) |

### Inventory
- Basic tools (Axe, Hoe, Watering Can, Pickaxe, Scythe)
- Seeds (15 Parsnip Seeds, 1 Mixed Seeds)
- Resources (162 Fiber, 20 Stone)

### Relationships
- **Lewis**: 0 friendship points
- **Robin**: 0 friendship points
- No marriages, no romances yet

### Quests Active
- **Introductions**: Meet 28 townspeople (2/28 progress)
- **Getting Started**: Cultivate and harvest a parsnip

### Statistics
- Days played: 2
- Steps taken: 577
- Rocks crushed: 20
- Average bedtime: 19:30

## Data Extraction Method

The `parse_save.py` script:
1. Parses the XML save files
2. Extracts all XML elements and attributes
3. Creates formatted Excel spreadsheet with:
   - Attribute names (XML paths)
   - Current values
   - Data types (Element vs Attribute)
4. Generates `Stardew_Save_Attributes.xlsx` with 789 total attributes

## Next Steps

- [ ] Continue farm development
- [ ] Build relationships with NPCs
- [ ] Expand farm infrastructure
- [ ] Develop crop production
- [ ] Create additional save analysis tools

## Files Ready for Future Development

This repository is set up for:
- Automated save analysis and visualization
- Relationship tracking and recommendations
- Farm optimization tools
- Time series analysis of farm progression

---

**Created**: March 3, 2026  
**Game Version**: Stardew Valley 1.6.15  
**Python Scripts**: Tested with Python 3.13
