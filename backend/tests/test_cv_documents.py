"""Synthetic resume regressions; no personal documents or outbound AI calls."""
from cv.service import normalized
import io
from uuid import uuid4
from unittest.mock import MagicMock
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject,ArrayObject,FloatObject,TextStringObject
from cv.document import normalize_text,text_document
from cv.extraction import extract_document
from cv.layout import extract_layout
from cv.grounding import GroundedAnalysis,GroundingError,validate_grounding
from test_cv import pdf_request,analysis,request,saved


def layout_pdf(pages, *, link=False, image=False, table=False, ligature=False):
    """Positioned synthetic text, deliberately emitted in caller-supplied order."""
    writer=PdfWriter()
    font=DictionaryObject({NameObject("/Type"):NameObject("/Font"),NameObject("/Subtype"):NameObject("/Type1"),
        NameObject("/BaseFont"):NameObject("/Helvetica"),NameObject("/Encoding"):NameObject("/WinAnsiEncoding")})
    if ligature:
        cmap=DecodedStreamObject();cmap.set_data(b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /Synthetic def /CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange 1 beginbfchar <80> <FB01> endbfchar endcmap CMapName currentdict /CMap defineresource pop end end")
        font[NameObject("/ToUnicode")]=writer._add_object(cmap)
    for rows in pages:
        page=writer.add_blank_page(width=600,height=800)
        page[NameObject("/Resources")]=DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):writer._add_object(font)})})
        commands=[]
        if table:
            for y in (115,135,155,175,195):commands.append(f"35 {800-y} m 520 {800-y} l S")
            for x in (35,300,520):commands.append(f"{x} 605 m {x} 685 l S")
        for x,y,text in rows:
            raw=text.encode("cp1252").hex()
            commands.append(f"BT /F1 10 Tf 1 0 0 1 {x} {800-y} Tm <{raw}> Tj ET")
        if image:
            stream=DecodedStreamObject();stream.set_data(bytes([120,120,120]))
            stream.update({NameObject("/Type"):NameObject("/XObject"),NameObject("/Subtype"):NameObject("/Image"),
                NameObject("/Width"):FloatObject(1),NameObject("/Height"):FloatObject(1),NameObject("/BitsPerComponent"):FloatObject(8),NameObject("/ColorSpace"):NameObject("/DeviceRGB")})
            page["/Resources"][NameObject("/XObject")]=DictionaryObject({NameObject("/Im1"):writer._add_object(stream)})
            commands.append("q 30 0 0 30 500 740 cm /Im1 Do Q")
        stream=DecodedStreamObject();stream.set_data("\n".join(commands).encode());page[NameObject("/Contents")]=writer._add_object(stream)
        if link:
            annotation=DictionaryObject({NameObject("/Type"):NameObject("/Annot"),NameObject("/Subtype"):NameObject("/Link"),
                NameObject("/Rect"):ArrayObject([FloatObject(v) for v in (40,700,200,720)]),
                NameObject("/A"):DictionaryObject({NameObject("/S"):NameObject("/URI"),NameObject("/URI"):TextStringObject("https://example.invalid/never-fetched")})})
            page[NameObject("/Annots")]=ArrayObject([writer._add_object(annotation)])
    out=io.BytesIO();writer.write(out);return out.getvalue()


def column(x,heading,company,technology):
    return [(x,100,heading),(x,120,company),(x,140,"2021 - 2024"),(x,160,f"Built reliable {technology} applications."),
            (x,180,"Documented technical contributions."),(x,200,"Improved readable error messages.")]


@pytest.mark.parametrize("raw,expected",[("Ger-\nmany","Germany"),("Vision-\nLib","VisionLib"),
    ("conﬁguration","configuration"),("Full-\nStack","Full-Stack"),("AI/ML C#/.NET C++ Next.js LangChain","AI/ML C#/.NET C++ Next.js LangChain"),
    ("Soft\u00adhyphen","Softhyphen"),("“Python” • .NET","\"Python\" - .NET")])
def test_conservative_normalization(raw,expected):
    assert normalize_text(raw)==expected


@pytest.mark.parametrize("count",[1,2,3])
def test_dynamic_columns_keep_sections_and_employers_separate(count):
    columns=[column(35,"Professional Experience","Example Employer","C#/.NET"),
             column(330 if count==2 else 220,"Projects","Example Project","Unity"),column(420,"Training","Example Course","Python")][:count]
    # Interleave content-stream order, like many design-tool exports.
    rows=[entry for row in zip(*columns) for entry in row]
    doc=extract_layout(layout_pdf([rows]))
    for index,expected in enumerate(("experience","projects","training")[:count]):
        blocks=[b for b in doc.blocks if b.section==expected]
        assert blocks and all(other not in blocks[0].text for other in ("Example Employer","Example Project","Example Course") if other!=columns[index][1][2])
        assert columns[index][1][2] in blocks[0].text and "2021 - 2024" in blocks[0].text
    assert doc.blocks[0].page==1 and doc.blocks[0].bbox


def test_narrow_sidebar_and_repeated_headings():
    left=column(35,"Experience","Example Employer","Angular")
    right=column(330,"Technical Skills","Skill list","Python")
    doc=extract_layout(layout_pdf([left+right,left+right]))
    assert doc.page_count==2
    assert {b.page for b in doc.blocks if b.section=="experience"}=={1,2}
    assert len({b.source_id for b in doc.blocks})==len(doc.blocks)


def test_table_dates_stay_on_employer_rows():
    rows=[(35,100,"Experience"),(35,120,"Employer"),(400,120,"Dates")]
    for y,company,dates in [(145,"Example Alpha","2018 - 2019"),(165,"Example Beta","2020 - 2021"),(185,"Example Gamma","2022 - 2024")]:
        rows.extend([(35,y,company),(400,y,dates)])
    doc=extract_layout(layout_pdf([rows]))
    assert any(b.section=="experience" for b in doc.blocks)
    for company,dates in [("Example Alpha","2018 - 2019"),("Example Beta","2020 - 2021"),("Example Gamma","2022 - 2024")]:
        assert any(company in line["original"] and dates in line["original"] for b in doc.blocks for line in b.lines)


def test_images_links_german_bullets_and_wrapped_words():
    rows=[(35,80,"Berufserfahrung"),(35,100,"Example Employer 2020 - 2024"),(35,120,"\u2022 Entwickelte C#/.NET und C++ Anwendungen in Ger-"),
          (35,134,"many mit Vision-"),(35,148,"Lib und Python für größere Anwendungen."),(35,180,"Sprachen"),(35,200,"Deutsch und Englisch")]
    doc=extract_document(pdf_request(layout_pdf([rows],image=True,link=True)))
    assert "Germany mit VisionLib" in doc.text
    assert {"experience","languages"}<={b.section for b in doc.blocks}
    assert "C#/.NET" in doc.text and "C++" in doc.text
    assert "größere" in doc.text
    assert all(b.original and b.lines for b in doc.blocks)


def test_image_only_is_rejected_without_ocr():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:extract_document(pdf_request(layout_pdf([[]],image=True)))
    assert exc.value.status_code==422 and "OCR" in exc.value.detail


def test_grounding_normalization_and_unknown_or_paraphrased_quotes():
    doc=text_document("Experience\nBuilt C#/.NET applications in Ger-\nmany with Vision-\nLib and tested conﬁguration changes.")
    a=analysis();a.strengths[0].source_id=doc.blocks[0].source_id;a.strengths[0].evidence="Germany with VisionLib"
    validate_grounding(a,doc)
    a.strengths[0].evidence="Paraphrased experience with a German library"
    with pytest.raises(GroundingError):validate_grounding(a,doc)
    a.strengths[0].source_id="invented_id"
    with pytest.raises(GroundingError,match="Source validation"):validate_grounding(a,doc)


def test_wrong_section_and_substantive_rewrite_are_rejected():
    from cv.schemas import Rewrite
    doc=text_document("Training\nLearned Python during a software development course, with practical projects and validation tests.")
    a=analysis();item=a.strengths[0];item.source_id=doc.blocks[0].source_id;item.evidence="Learned Python";item.title="Relevant professional experience"
    with pytest.raises(GroundingError) as exc:validate_grounding(a,doc)
    assert exc.value.code=="section_claim_mismatch"
    item.title="Education or training"
    a.rewrites=[Rewrite(source_id=item.source_id,original="Learned Python",suggested="Led AWS engineering teams",rationale="Unsupported")]
    validate_grounding(a,doc)
    assert not a.rewrites and "unsupported_rewrite_omitted" in doc.warnings


def test_source_contract_rejects_invented_qualification_titles():
    from pydantic import ValidationError
    value=analysis().model_dump();value["strengths"][0]["title"]="Certified AWS architect with ten years of experience"
    with pytest.raises(ValidationError):GroundedAnalysis.model_validate(value)


def test_skill_absence_is_not_a_claim_about_the_person():
    from cv.schemas import MissingSkill
    doc=text_document("Skills\nPython, SQL, Git and automated tests. Developed documented backend applications with readable validation errors.")
    a=analysis();a.strengths=[]
    a.missing_skills=[MissingSkill(skill="AWS",reason="The candidate has no AWS knowledge",evidence_status="not_evidenced",recommendation="Consider learning AWS if relevant to your goals.")]
    validate_grounding(a,doc)
    assert "no AWS knowledge" not in a.missing_skills[0].reason
    assert "does not establish whether you possess it" in a.missing_skills[0].reason
    a.missing_skills[0].evidence_status="partially_evidenced"
    validate_grounding(a,doc)
    assert a.missing_skills[0].evidence_status=="not_evidenced"
    doc=text_document("Skills\nAmazon Web Services, Python, SQL, Git and automated tests. Developed backend applications with readable validation errors.")
    a.missing_skills[0].evidence_status="not_evidenced"
    validate_grounding(a,doc)
    assert not a.missing_skills and "skill_presence_corrected" in doc.warnings


def test_bad_citation_gets_one_bounded_model_correction():
    from types import SimpleNamespace
    from interviews.llm import NvidiaInterviewer
    from test_interviews import mock_client
    doc=text_document("Skills\nPython, SQL and Git. Built tested backend applications with clear documentation and readable errors.")
    a=analysis().model_dump();a["strengths"][0].update(evidence="Python, SQL and Git",source_id=doc.blocks[0].source_id)
    valid=GroundedAnalysis.model_validate(a)
    invalid=valid.model_copy(deep=True);invalid.strengths[0].evidence="Invented AWS certification"
    client=mock_client("")
    response=lambda value:SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value.model_dump_json()))])
    client.chat.completions.create.side_effect=[response(invalid),response(valid)]
    result=NvidiaInterviewer(lambda:client).generate_json("Review sources",doc.payload(),GroundedAnalysis,validator=lambda item:validate_grounding(item,doc))
    assert result.strengths[0].evidence=="Python, SQL and Git"
    assert client.chat.completions.create.call_count==2
    client.chat.completions.create.reset_mock(side_effect=True);client.chat.completions.create.return_value=response(invalid)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:NvidiaInterviewer(lambda:client).generate_json("Review sources",doc.payload(),GroundedAnalysis,validator=lambda item:validate_grounding(item,doc))
    assert exc.value.status_code==502 and client.chat.completions.create.call_count==2


def test_bordered_table_keeps_text_cells_on_the_same_row():
    rows=[(35,95,"Professional Experience"),(45,128,"Example Alpha"),(310,128,"Backend Developer"),
          (45,148,"Example Beta"),(310,148,"Frontend Developer"),(45,168,"Example Gamma"),(310,168,"Data Engineer")]
    doc=extract_layout(layout_pdf([rows],table=True))
    for company,role in [("Example Alpha","Backend Developer"),("Example Beta","Frontend Developer"),("Example Gamma","Data Engineer")]:
        assert any(company in line["original"] and role in line["original"] for b in doc.blocks for line in b.lines)


def test_uncertain_short_columns_remain_separate_with_a_warning():
    rows=[(35,90,"Experience"),(35,120,"Example Employer"),(350,120,"Unrelated project"),
          (35,140,"Python API delivery"),(350,140,"Unity training course")]
    doc=extract_layout(layout_pdf([rows]))
    assert doc.confidence=="low" and "ambiguous_row_cells" in doc.warnings
    assert all(not("Example Employer" in b.text and "Unrelated project" in b.text) for b in doc.blocks)


def test_pdf_ligature_and_ten_page_cv():
    rows=column(35,"Skills","Synthetic con€guration","Python")
    doc=extract_document(pdf_request(layout_pdf([rows]*10,ligature=True)))
    assert doc.page_count==10 and "configuration" in doc.text
    assert len({b.source_id for b in doc.blocks})==len(doc.blocks)


def test_pdf_workflow_validates_before_persistence_without_saving_source():
    from cv.service import CvService
    rows=column(35,"Experience","Example Employer","Python")
    req=pdf_request(layout_pdf([rows]));doc=extract_document(req);a=analysis()
    a.strengths[0].source_id=doc.blocks[0].source_id;a.strengths[0].evidence="Built reliable Python applications."
    repo=MagicMock();repo.claim.return_value=(saved(req,"processing"),uuid4());repo.complete.side_effect=lambda id,owner,fence,value:value
    llm=MagicMock();llm.generate_json.return_value=a
    result=CvService(repo,llm).review(req,"a"*43)
    assert result.strengths[0].source_page==1 and result.strengths[0].source_section=="experience"
    assert "Example Employer" not in str(repo.complete.call_args)
    assert "Example Employer" not in str(repo.claim.call_args)


def test_wrapped_source_quote_regression():
    source = "Built C#/.NET applications in Ger-\nmany with Vision-\nLib."
    assert normalized("Germany with VisionLib") in normalized(source)
