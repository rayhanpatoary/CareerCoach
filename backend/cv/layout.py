"""Coordinate-based, template-independent reading order using pdfminer.six.

No rendering, OCR or image decoding. All coordinates remain request-local.
"""
from statistics import median
from collections import Counter
import re

from .document import ResumeDocument, SourceBlock, normalize_text, section_heading


def _bounds(lines):
    return [min(v["bbox"][0] for v in lines), min(v["bbox"][1] for v in lines),
            max(v["bbox"][2] for v in lines), max(v["bbox"][3] for v in lines)]


def page_lines(page):
    from pdfminer.layout import LTChar, LTTextLineHorizontal, LTTextLineVertical
    result, rotated = [], False
    def visit(node):
        nonlocal rotated
        if isinstance(node, LTTextLineVertical):rotated=True;return
        if isinstance(node, LTTextLineHorizontal):
            pieces, chars, last = [], [], None
            def flush():
                if chars:
                    text="".join(c.get_text() if isinstance(c,LTChar) else " " for c in chars).strip()
                    glyphs=[c for c in chars if isinstance(c,LTChar)]
                    if text and glyphs:
                        pieces.append({"original":text,"bbox":[min(c.x0 for c in glyphs),page.height-max(c.y1 for c in glyphs),
                            max(c.x1 for c in glyphs),page.height-min(c.y0 for c in glyphs)],"size":median(c.size for c in glyphs)})
                    chars.clear()
            for char in node:
                if isinstance(char,LTChar):
                    if last is not None and char.x0-last.x1>max(16,char.size*1.8):flush()
                    chars.append(char);last=char
                else:chars.append(char)
            flush();result.extend(pieces)
        elif hasattr(node,"__iter__"):
            for child in node:visit(child)
    visit(page)
    # Duplicate overprinted text is common in PDFs; deduplicate geometry + text only.
    unique={}
    for line in result:
        key=(line["original"],tuple(round(v,1) for v in line["bbox"]))
        unique.setdefault(key,line)
    return list(unique.values()), rotated


def _cut(lines):
    if len(lines)<6:return None
    size=median(v["size"] for v in lines)
    x0,y0,x1,y1=_bounds(lines);width=x1-x0
    edges=sorted(set(v["bbox"][i] for v in lines for i in (0,2)))
    candidates=[]
    for a,b in zip(edges,edges[1:]):
        if b-a<max(4,size*.6):continue
        cut=(a+b)/2
        if min(cut-x0,x1-cut)<width*.13:continue
        left=[v for v in lines if v["bbox"][2]<=cut]
        right=[v for v in lines if v["bbox"][0]>=cut]
        crossing=[v for v in lines if v not in left and v not in right]
        if min(len(left),len(right))<3 or len(crossing)>max(2,len(lines)*.12):continue
        # Dates aligned beside employers belong to the same rows, not a sidebar.
        date=lambda v:bool(re.fullmatch(r"[\d\s./–—\-]+(?:present|heute|aktuell)?",normalize_text(v["original"],fold=True)))
        if sum(date(v) for v in right)/len(right)>.6:continue
        overlap=min(max(v["bbox"][3] for v in left),max(v["bbox"][3] for v in right))-max(min(v["bbox"][1] for v in left),min(v["bbox"][1] for v in right))
        if overlap<max(size*3,(y1-y0)*.25):continue
        candidates.append(((b-a)*min(len(left),len(right))/(len(crossing)+1),left,right,crossing))
    return max(candidates,key=lambda v:v[0])[1:] if candidates else None


def reading_regions(lines, depth=0):
    """Whitespace XY cuts, with spanning headings treated as horizontal bands."""
    if depth>=2:return [sorted(lines,key=lambda v:(round(v["bbox"][1]/3),v["bbox"][0]))]
    split=_cut(lines)
    if not split:return [sorted(lines,key=lambda v:(round(v["bbox"][1]/3),v["bbox"][0]))]
    left,right,spanning=split
    if spanning:
        regions=[];remaining=left+right
        for heading in sorted(spanning,key=lambda v:v["bbox"][1]):
            above=[v for v in remaining if v["bbox"][1]<heading["bbox"][1]]
            if above:regions.extend(reading_regions(above,depth))
            regions.append([heading]);remaining=[v for v in remaining if v not in above]
        if remaining:regions.extend(reading_regions(remaining,depth))
        return regions
    return reading_regions(left,depth+1)+reading_regions(right,depth+1)


def _table_rows(page,lines):
    """Only explicit connected grids establish table rows; whitespace alone cannot."""
    from pdfminer.layout import LTLine,LTRect
    rules=[]
    def collect(node):
        if isinstance(node,LTLine):
            if abs(node.x1-node.x0)<1 or abs(node.y1-node.y0)<1:
                rules.append([node.x0,page.height-node.y1,node.x1,page.height-node.y0])
        elif isinstance(node,LTRect):
            a,b,c,d=node.x0,page.height-node.y1,node.x1,page.height-node.y0
            rules.extend([[a,b,c,b],[a,d,c,d],[a,b,a,d],[c,b,c,d]])
        elif hasattr(node,"__iter__"):
            for child in node:collect(child)
    collect(page)
    if len(rules)>500:return lines,True
    groups=[]
    for rule in rules:
        touching=[g for g in groups if any(not (rule[2]+1<v[0] or v[2]+1<rule[0] or rule[3]+1<v[1] or v[3]+1<rule[1]) for v in g)]
        merged=[rule]
        for g in touching:merged.extend(g);groups.remove(g)
        groups.append(merged)
    for grid in groups:
        horizontal=[v for v in grid if v[3]-v[1]<1 and v[2]-v[0]>20]
        vertical=[v for v in grid if v[2]-v[0]<1 and v[3]-v[1]>20]
        if len(horizontal)<3 or len(vertical)<3:continue
        a=min(v[0] for v in grid);b=min(v[1] for v in grid);c=max(v[2] for v in grid);d=max(v[3] for v in grid)
        cells=[v for v in lines if a-1<=v["bbox"][0] and v["bbox"][2]<=c+1 and b-1<=v["bbox"][1] and v["bbox"][3]<=d+1]
        rows=[]
        for line in sorted(cells,key=lambda v:(round(v["bbox"][3]/3),v["bbox"][0])):
            if rows and abs(line["bbox"][3]-rows[-1]["bbox"][3])<line["size"]*.45:
                rows[-1]["original"]+="\t"+line["original"];rows[-1]["bbox"]=_bounds([rows[-1],line])
            else:rows.append({**line,"bbox":list(line["bbox"])})
        lines=[v for v in lines if v not in cells]+rows
    return lines,False


def extract_layout(data):
    import io
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams
    blocks,warnings=[],[];pages=0
    for number,page in enumerate(extract_pages(io.BytesIO(data),laparams=LAParams(
            boxes_flow=None,char_margin=1.0,line_margin=.15,detect_vertical=True,all_texts=True)),1):
        pages=number
        if number>10:raise ValueError("Page limit")
        lines,rotated=page_lines(page)
        expected=Counter(re.sub(r"\s+","","".join(v["original"] for v in lines)))
        lines,complex_grid=_table_rows(page,lines)
        if complex_grid:warnings.append("complex_table_geometry")
        if rotated:warnings.append("rotated_text_not_supported")
        if sum(len(v["original"]) for v in lines)>30000:raise ValueError("Text limit")
        page_start=len(blocks)
        regions=reading_regions(lines)
        for column,region in enumerate(regions,1):
            # Rejoin justified text fragments only AFTER separating columns.
            joined=[]
            for line in region:
                if joined and abs(line["bbox"][3]-joined[-1]["bbox"][3])<min(line["size"],joined[-1]["size"])*.45:
                    previous=joined[-1]
                    gap=line["bbox"][0]-previous["bbox"][2]
                    cell_text=normalize_text(line["original"],fold=True)
                    date_cell=cell_text in {"dates","date","datum","zeitraum","period","duration"} or bool(re.fullmatch(r"[\d\s./–—-]+(?:present|heute|aktuell)?",cell_text))
                    ambiguous=len(regions)==1 and gap>line["size"]*1.8 and not date_cell
                    if gap>=0 and not ambiguous:
                        previous["original"]+=" "+line["original"]
                        previous["bbox"]=_bounds([previous,line])
                        continue
                joined.append({**line,"bbox":list(line["bbox"])})
            region=joined
            section="unclassified";pending=[]
            def flush():
                if not pending:return
                raw="\n".join(v["original"] for v in pending)
                blocks.append(SourceBlock(f"p{number:02d}_r{column:02d}_b{len(blocks)+1:03d}",raw,
                    normalize_text(raw),section,number,column,_bounds(pending),list(pending)))
                pending.clear()
            for line in region:
                heading=section_heading(line["original"])
                side_by_side=pending and line["bbox"][1]<pending[-1]["bbox"][3] and line["bbox"][0]>pending[-1]["bbox"][2]+line["size"]
                if side_by_side:
                    # Keep cells separate, rather than merge unrelated side-by-side content.
                    warnings.append("ambiguous_row_cells");flush();section="unclassified"
                if heading:flush();section=heading
                if pending and sum(len(v["original"]) for v in pending)+len(line["original"])>1800:flush()
                pending.append(line)
            flush()
        actual=Counter(re.sub(r"\s+","","".join(b.original for b in blocks[page_start:])))
        if actual!=expected:raise ValueError("Unassigned source glyphs")
        page.close() if hasattr(page,"close") else None
    if sum(len(v.original) for v in blocks)>30000:raise ValueError("Text limit")
    return ResumeDocument(blocks,"pdf",pages,"low" if warnings else "medium",list(dict.fromkeys(warnings)))
