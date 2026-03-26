import React, { FC, ReactNode } from 'react';
import { Button as AntdButton, Form as AntdForm, Tooltip as AntdTooltip } from 'antd';

// Button shim
export const Button = AntdButton;

// Tooltip shim
export type TooltipProps = React.ComponentProps<typeof AntdTooltip>;
export const Tooltip = AntdTooltip as unknown as React.ComponentType<TooltipProps>;

// Icon shim: renders a passed icon component with props
export const Icon: FC<{ icon: any; size?: number | string; style?: React.CSSProperties } & any> = ({ icon: Cmp, size, style, ...rest }) => {
  const s: React.CSSProperties = {
    width: typeof size === 'number' ? size : undefined,
    height: typeof size === 'number' ? size : undefined,
    fontSize: typeof size === 'number' ? size : size,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    ...style,
  };
  return Cmp ? <Cmp style={s} {...rest} /> : null;
};

// Minimal Form shim that supports items array and basic props used in Lobe ControlsForm
export type FormItemProps = {
  name?: any;
  label?: ReactNode;
  children?: ReactNode;
  style?: React.CSSProperties;
  desc?: ReactNode;
  layout?: 'vertical' | 'horizontal';
  minWidth?: number | undefined;
  tag?: string;
};

export type FormProps = React.ComponentProps<typeof AntdForm> & {
  items?: FormItemProps[];
  itemsType?: 'flat' | 'grid';
  variant?: 'borderless' | 'filled';
};

const FormInner: FC<FormProps> = (props: FormProps) => {
  const { items, children, ...rest } = props;
  if (!items) return <AntdForm {...(rest as any)}>{children}</AntdForm>;
  return (
    <AntdForm {...(rest as any)}>
      {items.map((item, idx) => (
        <AntdForm.Item key={idx} name={item.name as any} label={item.label as any} style={item.style}>
          {/* Render description above the control if provided */}
          {item.desc ? <div style={{ marginBottom: 6 }}>{item.desc}</div> : null}
          {item.children}
        </AntdForm.Item>
      ))}
      {children}
    </AntdForm>
  );
};

export const Form = Object.assign(FormInner, { useForm: AntdForm.useForm });

// Typography shim used by mdx wrapper
export type TypographyProps = React.HTMLAttributes<HTMLDivElement> & {
  fontSize?: number;
  headerMultiple?: number;
};

export const Typography: FC<TypographyProps> = ({ children, style, ...rest }) => (
  <div style={style} {...(rest as any)}>{children}</div>
);
