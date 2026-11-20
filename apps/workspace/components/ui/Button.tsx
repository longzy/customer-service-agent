"use client";

import { Button as HeroButton, type ButtonProps as HeroButtonProps } from "@heroui/react";

type ButtonProps = Omit<HeroButtonProps, "className" | "variant" | "size"> & {
  variant?: "primary" | "secondary" | "ghost" | "soft" | "danger";
  size?: "sm" | "md" | "lg";
  className?: string;
  /** 兼容既有调用；HeroUI/RAC 的原生属性名为 isDisabled */
  disabled?: boolean;
};

const HERO_VARIANT = {
  primary: "primary",
  secondary: "secondary",
  ghost: "ghost",
  soft: "ghost",
  danger: "danger",
} as const;

const VARIANTS = {
  primary:
    "border-accent bg-accent text-white shadow-panel hover:border-accent/90 hover:bg-accent/90",
  secondary: "border-border bg-surface text-text hover:border-border-strong hover:bg-surface-2",
  ghost: "border-transparent bg-transparent text-text-2 hover:bg-surface-2 hover:text-text",
  soft: "border-transparent bg-accent-soft text-accent-ink hover:bg-accent-line",
  danger: "border-danger bg-danger text-white hover:bg-danger/90",
};

const BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-lg border font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-text-3 disabled:shadow-none";

const SIZES = {
  sm: "h-[30px] px-3 text-xs",
  md: "h-9 px-4 text-sm",
  lg: "h-11 rounded-lg px-5 text-base",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  type = "button",
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <HeroButton
      type={type}
      variant={HERO_VARIANT[variant]}
      size={size === "lg" ? "lg" : "md"}
      isDisabled={disabled}
      aria-disabled={disabled || undefined}
      className={[BASE, VARIANTS[variant], SIZES[size], className].filter(Boolean).join(" ")}
      {...rest}
    />
  );
}
