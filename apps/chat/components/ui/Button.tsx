"use client";

import type { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  size?: "md" | "lg";
};

const VARIANTS = {
  primary: "border-accent bg-accent text-surface hover:bg-brand-deep",
  secondary: "border-border-strong bg-surface text-text-2 hover:border-text-3",
  ghost: "border-transparent bg-transparent text-text-2 hover:text-text",
};

const BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-md border font-medium transition-colors focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-text-3";

const SIZES = {
  md: "h-[38px] px-3.5 text-sm",
  lg: "h-[42px] rounded-lg px-3.5 text-base",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={[BASE, VARIANTS[variant], SIZES[size], className].filter(Boolean).join(" ")}
      {...rest}
    />
  );
}
