"""Pydantic request/response models for the whole API."""

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


# --------------------------------------------------------------------------- #
# Shared
# --------------------------------------------------------------------------- #
class Frequency(str, Enum):
    one_time = "one_time"
    monthly = "monthly"
    quarterly = "quarterly"
    term = "term"
    annual = "annual"


class PaymentMode(str, Enum):
    cash = "cash"
    upi = "upi"
    card = "card"
    cheque = "cheque"
    bank_transfer = "bank_transfer"


class Role(str, Enum):
    admin = "admin"
    staff = "staff"
    teacher = "teacher"


class StudentStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    graduated = "graduated"


class FeeCategory(str, Enum):
    """Why a child pays what they pay.

    Everything except ``regular`` is a full waiver: picking one zeroes the
    payable fee, so these children never appear in the dues list. The category
    is kept on the record so the trust can report on how many free seats each
    kind of concession accounts for.
    """

    regular = "regular"
    staff_ward = "staff_ward"
    management_ward = "management_ward"
    govt_quota = "govt_quota"
    financial_aid = "financial_aid"


FREE_FEE_CATEGORIES: frozenset[FeeCategory] = frozenset(
    c for c in FeeCategory if c is not FeeCategory.regular
)

FEE_CATEGORY_LABELS: dict[str, str] = {
    FeeCategory.regular.value: "Regular",
    FeeCategory.staff_ward.value: "Staff ward",
    FeeCategory.management_ward.value: "Management / Principal's ward",
    FeeCategory.govt_quota.value: "Govt quota / RTE",
    FeeCategory.financial_aid.value: "Financial aid",
}


def is_free_category(value: str | None) -> bool:
    return bool(value) and value != FeeCategory.regular.value


class AttendanceStatus(str, Enum):
    present = "present"
    absent = "absent"
    late = "late"
    holiday = "holiday"


class FeeComponent(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    amount: float = Field(ge=0)
    frequency: Frequency = Frequency.annual


class Installment(BaseModel):
    label: str
    due_date: date
    amount: float
    items: list[FeeComponent] = []


# --------------------------------------------------------------------------- #
# Auth / users
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    role: Role = Role.staff
    phone: str | None = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=128)


class UserUpdate(BaseModel):
    name: str | None = None
    role: Role | None = None
    phone: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)


class UserOut(UserBase):
    id: str
    created_at: datetime | None = None


# --------------------------------------------------------------------------- #
# Classrooms
# --------------------------------------------------------------------------- #
class ClassroomBase(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    level: str = Field(default="Nursery", max_length=40)
    room: str | None = None
    capacity: int = Field(default=20, ge=1, le=200)
    academic_year: str | None = None
    class_teacher_id: str | None = None
    fee_components: list[FeeComponent] = []


class ClassroomCreate(ClassroomBase):
    pass


class ClassroomUpdate(BaseModel):
    name: str | None = None
    level: str | None = None
    room: str | None = None
    capacity: int | None = Field(default=None, ge=1, le=200)
    academic_year: str | None = None
    class_teacher_id: str | None = None
    fee_components: list[FeeComponent] | None = None


class ClassroomOut(ClassroomBase):
    id: str
    student_count: int = 0
    class_teacher_name: str | None = None
    annual_fee: float = 0


# --------------------------------------------------------------------------- #
# Students
# --------------------------------------------------------------------------- #
class GuardianInfo(BaseModel):
    father_name: str | None = None
    father_occupation: str | None = None
    mother_name: str | None = None
    mother_occupation: str | None = None
    guardian_name: str | None = None
    relation: str | None = None
    primary_phone: str = Field(min_length=6, max_length=20)
    alternate_phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None


class MedicalInfo(BaseModel):
    blood_group: str | None = None
    allergies: str | None = None
    conditions: str | None = None
    doctor_name: str | None = None
    doctor_phone: str | None = None


class StudentBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str | None = Field(default=None, max_length=60)
    gender: Literal["male", "female", "other"] = "male"
    date_of_birth: date
    classroom_id: str | None = None
    admission_date: date | None = None
    status: StudentStatus = StudentStatus.active
    fee_category: FeeCategory = FeeCategory.regular
    photo_url: str | None = None
    guardian: GuardianInfo
    medical: MedicalInfo = MedicalInfo()
    transport_opted: bool = False
    transport_route: str | None = None
    notes: str | None = None

    @field_validator("date_of_birth")
    @classmethod
    def dob_in_past(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return v


class InitialPayment(BaseModel):
    """First instalment, collected at the enrolment desk."""

    amount: float = Field(gt=0)
    mode: PaymentMode = PaymentMode.cash
    paid_on: date | None = None
    reference: str | None = Field(default=None, max_length=80)
    remarks: str | None = Field(default="Initial admission payment", max_length=300)
    particulars: str | None = Field(default=None, max_length=120)


class StudentCreate(StudentBase):
    admission_no: str | None = None  # auto-generated when omitted

    # Fee agreed with the parents at admission. When omitted the class's
    # standard fee structure total is used as-is.
    agreed_fee: float | None = Field(default=None, ge=0)
    fee_note: str | None = Field(default=None, max_length=200)
    initial_payment: InitialPayment | None = None


class StudentUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    gender: Literal["male", "female", "other"] | None = None
    date_of_birth: date | None = None
    classroom_id: str | None = None
    admission_date: date | None = None
    status: StudentStatus | None = None
    fee_category: FeeCategory | None = None
    photo_url: str | None = None
    guardian: GuardianInfo | None = None
    medical: MedicalInfo | None = None
    transport_opted: bool | None = None
    transport_route: str | None = None
    notes: str | None = None


class FeePlanOut(BaseModel):
    academic_year: str
    items: list[FeeComponent] = []
    installments: list[Installment] = []
    gross: float = 0  # standard total from the class fee structure
    agreed_total: float = 0  # what was actually agreed with the parents
    discount: float = 0  # concession, when agreed < standard
    extra: float = 0  # additional agreed amount, when agreed > standard
    discount_reason: str | None = None
    net_payable: float = 0
    generated_at: datetime | None = None


class StudentFeeSummary(BaseModel):
    """Compact fee position, shown in list views so dues are visible at a glance."""

    net_payable: float = 0
    total_paid: float = 0
    balance: float = 0
    overdue_amount: float = 0
    next_due_date: date | None = None
    next_due_amount: float = 0


class StudentOut(StudentBase):
    id: str
    admission_no: str
    full_name: str
    age: float | None = None
    classroom_name: str | None = None
    created_at: datetime | None = None
    fee_plan: FeePlanOut | None = None
    fee_summary: StudentFeeSummary | None = None
    fee_category_label: str = FEE_CATEGORY_LABELS[FeeCategory.regular.value]
    # Set by the admin while collecting an instalment; overrides the date the
    # schedule would otherwise have computed.
    next_due_override: date | None = None


class StudentCreatedOut(StudentOut):
    """Enrolment response — carries the first receipt when one was collected."""

    initial_receipt: "PaymentOut | None" = None


class StudentListResponse(BaseModel):
    items: list[StudentOut]
    total: int
    page: int
    page_size: int
    totals: StudentFeeSummary | None = None  # fee position across the whole filter


# --------------------------------------------------------------------------- #
# Teachers
# --------------------------------------------------------------------------- #
class TeacherBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str | None = Field(default=None, max_length=60)
    gender: Literal["male", "female", "other"] = "female"
    date_of_birth: date | None = None
    phone: str = Field(min_length=6, max_length=20)
    email: EmailStr | None = None
    address: str | None = None
    qualification: str | None = None
    designation: str = "Class Teacher"
    subjects: list[str] = []
    date_of_joining: date | None = None
    salary: float = Field(default=0, ge=0)
    status: Literal["active", "inactive"] = "active"
    notes: str | None = None


class TeacherCreate(TeacherBase):
    employee_no: str | None = None


class TeacherUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    gender: Literal["male", "female", "other"] | None = None
    date_of_birth: date | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    qualification: str | None = None
    designation: str | None = None
    subjects: list[str] | None = None
    date_of_joining: date | None = None
    salary: float | None = Field(default=None, ge=0)
    status: Literal["active", "inactive"] | None = None
    notes: str | None = None


class TeacherOut(TeacherBase):
    id: str
    employee_no: str
    full_name: str
    classrooms: list[str] = []
    created_at: datetime | None = None


# --------------------------------------------------------------------------- #
# Fees & payments
# --------------------------------------------------------------------------- #
class FeePlanAssign(BaseModel):
    """Assign / regenerate a student's fee plan for an academic year."""

    academic_year: str | None = None
    use_classroom_structure: bool = True
    extra_items: list[FeeComponent] = []
    agreed_fee: float | None = Field(default=None, ge=0)
    discount: float = Field(default=0, ge=0)
    discount_reason: str | None = None
    # A concession category wins over agreed_fee and zeroes the plan.
    fee_category: FeeCategory | None = None


class PaymentItem(BaseModel):
    name: str
    amount: float = Field(ge=0)


class PaymentCreate(BaseModel):
    student_id: str
    amount: float = Field(gt=0)
    mode: PaymentMode = PaymentMode.cash
    paid_on: date | None = None
    reference: str | None = Field(default=None, max_length=80)
    remarks: str | None = Field(default=None, max_length=300)
    items: list[PaymentItem] | None = None  # defaults to auto-allocation
    # What the money is being collected for, e.g. "1st Term Fee". Printed as
    # the receipt's particulars. Omit to describe the payment from the
    # instalment schedule instead.
    particulars: str | None = Field(default=None, max_length=120)
    # When the desk agrees a date for the next instalment, it is recorded here
    # and replaces the auto-computed one. Omit to keep the automatic schedule.
    next_due_date: date | None = None


class PaymentOut(BaseModel):
    id: str
    receipt_no: str
    student_id: str
    student_name: str
    admission_no: str
    classroom_name: str | None = None
    academic_year: str
    amount: float
    mode: PaymentMode
    reference: str | None = None
    remarks: str | None = None
    items: list[PaymentItem] = []
    paid_on: datetime
    collected_by: str | None = None
    cancelled: bool = False
    cancel_reason: str | None = None
    balance_after: float = 0


class PaymentListResponse(BaseModel):
    items: list[PaymentOut]
    total: int
    page: int
    page_size: int
    total_amount: float = 0


class InstallmentStatus(Installment):
    paid: float = 0
    balance: float = 0
    status: Literal["paid", "partial", "due", "overdue"] = "due"


class LedgerResponse(BaseModel):
    student_id: str
    student_name: str
    admission_no: str
    classroom_name: str | None = None
    academic_year: str
    gross: float = 0
    discount: float = 0
    extra: float = 0
    net_payable: float = 0
    total_paid: float = 0
    balance: float = 0
    next_due: InstallmentStatus | None = None
    next_due_override: date | None = None
    installments: list[InstallmentStatus] = []
    payments: list[PaymentOut] = []


class ReceiptResponse(BaseModel):
    payment: PaymentOut
    school: dict
    amount_in_words: str
    total_paid: float
    net_payable: float
    balance: float


# --------------------------------------------------------------------------- #
# Attendance
# --------------------------------------------------------------------------- #
class AttendanceEntry(BaseModel):
    student_id: str
    status: AttendanceStatus = AttendanceStatus.present
    remarks: str | None = None


class AttendanceBulkCreate(BaseModel):
    classroom_id: str
    date: date
    entries: list[AttendanceEntry]


class AttendanceOut(BaseModel):
    id: str | None = None
    student_id: str
    student_name: str
    gender: Literal["male", "female", "other"] | None = None
    admission_no: str
    classroom_id: str | None = None
    date: date
    status: AttendanceStatus | None = None
    remarks: str | None = None


# --------------------------------------------------------------------------- #
# Dashboard / reports
# --------------------------------------------------------------------------- #
class DashboardStats(BaseModel):
    students_total: int = 0
    students_active: int = 0
    teachers_active: int = 0
    classrooms: int = 0
    fees_expected: float = 0
    fees_collected: float = 0
    fees_outstanding: float = 0
    collected_this_month: float = 0
    collected_today: float = 0
    attendance_today_present: int = 0
    attendance_today_marked: int = 0
    students_by_class: list[dict] = []
    collection_trend: list[dict] = []
    recent_payments: list[PaymentOut] = []
    recent_admissions: list[dict] = []


class DueRow(BaseModel):
    student_id: str
    admission_no: str
    student_name: str
    classroom_name: str | None = None
    guardian_phone: str | None = None
    net_payable: float = 0
    total_paid: float = 0
    balance: float = 0
    overdue_amount: float = 0
    next_due_date: date | None = None


TokenResponse.model_rebuild()
StudentCreatedOut.model_rebuild()
