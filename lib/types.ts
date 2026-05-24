export type VendorStatus = "draft" | "pending_review" | "live" | "suspended";

export type OnboardingStep =
  | "signup"
  | "kyc"
  | "bank"
  | "category"
  | "location"
  | "products"
  | "go-live"
  | "done";

export interface Vendor {
  id: string;
  email: string;
  phone: string;
  passwordHash: string;
  businessName: string;
  slug: string;
  description: string;
  category: string;
  logoUrl: string | null;
  bannerUrl: string | null;
  status: VendorStatus;
  onboardingStep: OnboardingStep;
  lat: number | null;
  lng: number | null;
  address: string | null;
  kyc: {
    idType: "passport" | "drivers_license" | "national_id" | null;
    idNumber: string | null;
    documentUrl: string | null;
    submittedAt: string | null;
  };
  bank: {
    accountHolder: string | null;
    bankName: string | null;
    accountNumber: string | null;
    routingNumber: string | null;
    country: string | null;
  };
  createdAt: string;
  updatedAt: string;
}

export interface Product {
  id: string;
  vendorId: string;
  name: string;
  description: string;
  priceCents: number;
  currency: string;
  imageUrl: string | null;
  isActive: boolean;
  createdAt: string;
}

export interface Category {
  id: string;
  name: string;
  icon: string;
  color: string;
}
