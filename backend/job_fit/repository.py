from cv.repository import CvRepository
from .tables import JobFitRecord
from .schemas import JobFitSummary,JobFitReview,JobFitHistory
from .saved_analysis import restore_analysis


class JobFitRepository(CvRepository):
    record_type=JobFitRecord
    summary_type=JobFitSummary
    view_type=JobFitReview
    history_type=JobFitHistory
    rate_namespace="job-fit"
    label="Job-fit analysis"

    @classmethod
    def _view(cls,row):
        fields={key:getattr(row,key) for key in cls.summary_type.model_fields}
        if row.status!="finished":return cls.view_type(**fields,analysis=None)
        try:analysis=restore_analysis(row.analysis)
        except (ValueError,TypeError,KeyError):
            return cls.view_type(**fields,analysis=None,legacy_notice="This older report has insufficient structured data to recalculate a reliable score. Start a fresh analysis with your CV and job posting.")
        return cls.view_type(**fields,analysis=analysis)
