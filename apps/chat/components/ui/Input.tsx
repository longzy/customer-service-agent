"use client";

import { Input as HeroInput, type InputProps as HeroInputProps } from "@heroui/react";
import type { Ref } from "react";

type InputProps = Omit<HeroInputProps, "className" | "ref"> & {
  className?: string;
  /** RAC TextField 的 ref 指向原生 input 元素 */
  inputRef?: Ref<HTMLInputElement>;
};

// 直接用 HeroUI 的 field 样式（1px 描边、10px 圆角、accent 焦点环），
// 只统一高度与字号；不再在外层包一层手写描边，避免双边框。
const BASE = "h-11 w-full text-base";

export function Input({ className = "", inputRef, ...rest }: InputProps) {
  return (
    <HeroInput ref={inputRef} className={[BASE, className].filter(Boolean).join(" ")} {...rest} />
  );
}
