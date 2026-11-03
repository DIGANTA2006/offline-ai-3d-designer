import Image from "next/image";
import Link from "next/link";

type BrandLogoProps = {
  className?: string;
  showName?: boolean;
};

/** Shared project brand mark for the public site and authenticated workspace. */
export function BrandLogo({ className = "", showName = true }: BrandLogoProps) {
  return (
    <Link
      href="/"
      aria-label="Offline AI 3D Designer home"
      className={`flex items-center gap-3 font-semibold tracking-tight ${className}`}
    >
      <span className="relative flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border bg-card">
        <Image
          src="/logo.png"
          alt=""
          fill
          sizes="40px"
          priority
          className="object-contain p-1"
        />
      </span>
      {showName && (
        <span className="leading-tight">
          Offline AI <span className="text-muted-foreground">3D Designer</span>
        </span>
      )}
    </Link>
  );
}
