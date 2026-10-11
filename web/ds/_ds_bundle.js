/* @ds-bundle: {"format":4,"namespace":"TharuniAssociatesDesignSystem_ce9184","components":[{"name":"Dialog","sourcePath":"components/feedback/Dialog.jsx"},{"name":"Toast","sourcePath":"components/feedback/Toast.jsx"},{"name":"Tooltip","sourcePath":"components/feedback/Tooltip.jsx"},{"name":"Button","sourcePath":"components/forms/Button.jsx"},{"name":"Checkbox","sourcePath":"components/forms/Checkbox.jsx"},{"name":"IconButton","sourcePath":"components/forms/IconButton.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Radio","sourcePath":"components/forms/Radio.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"},{"name":"Badge","sourcePath":"components/surfaces/Badge.jsx"},{"name":"Card","sourcePath":"components/surfaces/Card.jsx"},{"name":"Tabs","sourcePath":"components/surfaces/Tabs.jsx"},{"name":"Tag","sourcePath":"components/surfaces/Tag.jsx"}],"sourceHashes":{"components/feedback/Dialog.jsx":"5c52e48172b3","components/feedback/Toast.jsx":"81da002ab0cb","components/feedback/Tooltip.jsx":"f8634f0ef77d","components/forms/Button.jsx":"e9d90dcba6f7","components/forms/Checkbox.jsx":"93d4946bf6e3","components/forms/IconButton.jsx":"d9cd87de6b26","components/forms/Input.jsx":"d93c02a5bd83","components/forms/Radio.jsx":"d07dcce3b08b","components/forms/Select.jsx":"7ea954483401","components/forms/Switch.jsx":"5104b61796ec","components/surfaces/Badge.jsx":"99d9e792015c","components/surfaces/Card.jsx":"e14115a4e062","components/surfaces/Tabs.jsx":"d0962e21db76","components/surfaces/Tag.jsx":"3a5b670968d3"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.TharuniAssociatesDesignSystem_ce9184 = window.TharuniAssociatesDesignSystem_ce9184 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/feedback/Dialog.jsx
try { (() => {
/** Modal dialog. Render conditionally with open; footer takes action buttons. */
function Dialog({
  open,
  title,
  children,
  footer,
  onClose,
  width = 480
}) {
  if (!open) return null;
  return /*#__PURE__*/React.createElement("div", {
    onClick: onClose,
    style: {
      position: "fixed",
      inset: 0,
      background: "rgba(18, 26, 20, 0.45)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 100
    }
  }, /*#__PURE__*/React.createElement("div", {
    role: "dialog",
    "aria-modal": "true",
    onClick: e => e.stopPropagation(),
    style: {
      width,
      maxWidth: "calc(100vw - 48px)",
      background: "var(--white)",
      borderRadius: "var(--radius-xl)",
      boxShadow: "var(--shadow-lg)",
      padding: "var(--space-6)",
      fontFamily: "var(--font-body)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-start",
      justifyContent: "space-between",
      gap: "16px"
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      margin: 0,
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-xl)",
      color: "var(--text-heading)"
    }
  }, title), onClose && /*#__PURE__*/React.createElement("button", {
    onClick: onClose,
    "aria-label": "Close",
    style: {
      border: "none",
      background: "transparent",
      cursor: "pointer",
      fontSize: 20,
      color: "var(--text-muted)",
      lineHeight: 1,
      padding: 4
    }
  }, "\xD7")), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: "var(--space-4)",
      color: "var(--text-body)",
      fontSize: "var(--text-md)",
      lineHeight: "var(--leading-body)"
    }
  }, children), footer && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: "var(--space-6)",
      display: "flex",
      justifyContent: "flex-end",
      gap: "12px"
    }
  }, footer)));
}
Object.assign(__ds_scope, { Dialog });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Dialog.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Toast.jsx
try { (() => {
/** Inline toast/notification bar. tones: success | warning | danger | info */
function Toast({
  tone = "success",
  children,
  onDismiss,
  style
}) {
  const tones = {
    success: {
      background: "var(--green-100)",
      color: "var(--green-800)",
      border: "1px solid var(--green-200)"
    },
    warning: {
      background: "var(--amber-100)",
      color: "var(--amber-600)",
      border: "1px solid #EED9B8"
    },
    danger: {
      background: "var(--red-100)",
      color: "var(--red-600)",
      border: "1px solid #F0CFC8"
    },
    info: {
      background: "var(--sky-100)",
      color: "var(--sky-600)",
      border: "1px solid #CBE5F3"
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    role: "status",
    style: {
      display: "flex",
      alignItems: "center",
      gap: "12px",
      padding: "12px 16px",
      borderRadius: "var(--radius-md)",
      fontFamily: "var(--font-body)",
      fontSize: "var(--text-sm)",
      boxShadow: "var(--shadow-md)",
      ...tones[tone],
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1
    }
  }, children), onDismiss && /*#__PURE__*/React.createElement("button", {
    onClick: onDismiss,
    "aria-label": "Dismiss",
    style: {
      border: "none",
      background: "transparent",
      cursor: "pointer",
      color: "inherit",
      fontSize: 16,
      lineHeight: 1,
      padding: 2,
      opacity: 0.7
    }
  }, "\xD7"));
}
Object.assign(__ds_scope, { Toast });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Toast.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Tooltip.jsx
try { (() => {
/** Hover tooltip. Wraps its child; shows text above on hover. */
function Tooltip({
  text,
  children,
  style
}) {
  const [show, setShow] = React.useState(false);
  return /*#__PURE__*/React.createElement("span", {
    onMouseEnter: () => setShow(true),
    onMouseLeave: () => setShow(false),
    style: {
      position: "relative",
      display: "inline-flex",
      ...style
    }
  }, children, show && /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      bottom: "calc(100% + 8px)",
      left: "50%",
      transform: "translateX(-50%)",
      background: "var(--ink-900)",
      color: "var(--white)",
      padding: "6px 10px",
      borderRadius: "var(--radius-sm)",
      fontFamily: "var(--font-body)",
      fontSize: "var(--text-xs)",
      whiteSpace: "nowrap",
      boxShadow: "var(--shadow-md)",
      zIndex: 50
    }
  }, text));
}
Object.assign(__ds_scope, { Tooltip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Tooltip.jsx", error: String((e && e.message) || e) }); }

// components/forms/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Primary action button. variants: primary | secondary | ghost | danger; sizes: sm | md | lg */
function Button({
  variant = "primary",
  size = "md",
  disabled = false,
  children,
  style,
  ...rest
}) {
  const sizes = {
    sm: {
      padding: "6px 14px",
      fontSize: "var(--text-sm)"
    },
    md: {
      padding: "10px 20px",
      fontSize: "var(--text-md)"
    },
    lg: {
      padding: "14px 28px",
      fontSize: "var(--text-lg)"
    }
  };
  const variants = {
    primary: {
      background: "var(--brand)",
      color: "var(--text-on-brand)",
      border: "1px solid var(--brand)"
    },
    secondary: {
      background: "var(--white)",
      color: "var(--brand-strong)",
      border: "1px solid var(--border-brand)"
    },
    ghost: {
      background: "transparent",
      color: "var(--brand-strong)",
      border: "1px solid transparent"
    },
    danger: {
      background: "var(--state-danger)",
      color: "#fff",
      border: "1px solid var(--state-danger)"
    }
  };
  const [hover, setHover] = React.useState(false);
  const hoverFx = disabled ? {} : hover ? variant === "primary" ? {
    background: "var(--brand-strong)",
    borderColor: "var(--brand-strong)"
  } : variant === "secondary" ? {
    background: "var(--green-050)"
  } : variant === "ghost" ? {
    background: "var(--green-050)"
  } : {
    filter: "brightness(0.92)"
  } : {};
  return /*#__PURE__*/React.createElement("button", _extends({
    disabled: disabled,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      fontFamily: "var(--font-body)",
      fontWeight: "var(--weight-bold)",
      borderRadius: "var(--radius-pill)",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.45 : 1,
      transition: "background var(--duration-fast) var(--ease-out), transform var(--duration-fast) var(--ease-out)",
      display: "inline-flex",
      alignItems: "center",
      gap: "8px",
      ...sizes[size],
      ...variants[variant],
      ...hoverFx,
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Button.jsx", error: String((e && e.message) || e) }); }

// components/forms/Checkbox.jsx
try { (() => {
/** Checkbox with label. Controlled via checked/onChange or uncontrolled. */
function Checkbox({
  label,
  checked,
  defaultChecked,
  onChange,
  disabled = false,
  style
}) {
  const [internal, setInternal] = React.useState(!!defaultChecked);
  const isOn = checked !== undefined ? checked : internal;
  const toggle = e => {
    if (checked === undefined) setInternal(e.target.checked);
    onChange && onChange(e);
  };
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "10px",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.45 : 1,
      fontFamily: "var(--font-body)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      width: 20,
      height: 20,
      flex: "none"
    }
  }, /*#__PURE__*/React.createElement("input", {
    type: "checkbox",
    checked: isOn,
    onChange: toggle,
    disabled: disabled,
    style: {
      position: "absolute",
      inset: 0,
      opacity: 0,
      margin: 0,
      cursor: "inherit"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      inset: 0,
      borderRadius: "var(--radius-sm)",
      border: `1.5px solid ${isOn ? "var(--brand)" : "var(--border-default)"}`,
      background: isOn ? "var(--brand)" : "var(--white)",
      transition: "background var(--duration-fast) var(--ease-out)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, isOn && /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "10",
    viewBox: "0 0 12 10"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M1 5l3.5 3.5L11 1",
    fill: "none",
    stroke: "#fff",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  })))), label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-md)",
      color: "var(--text-body)"
    }
  }, label));
}
Object.assign(__ds_scope, { Checkbox });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Checkbox.jsx", error: String((e && e.message) || e) }); }

// components/forms/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Circular button holding a single icon (pass an SVG/glyph as children). */
function IconButton({
  variant = "secondary",
  size = "md",
  label,
  disabled = false,
  children,
  style,
  ...rest
}) {
  const dims = {
    sm: 32,
    md: 40,
    lg: 48
  };
  const variants = {
    primary: {
      background: "var(--brand)",
      color: "var(--text-on-brand)",
      border: "1px solid var(--brand)"
    },
    secondary: {
      background: "var(--white)",
      color: "var(--brand-strong)",
      border: "1px solid var(--border-default)"
    },
    ghost: {
      background: "transparent",
      color: "var(--brand-strong)",
      border: "1px solid transparent"
    }
  };
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", _extends({
    "aria-label": label,
    title: label,
    disabled: disabled,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      width: dims[size],
      height: dims[size],
      borderRadius: "50%",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.45 : 1,
      transition: "background var(--duration-fast) var(--ease-out)",
      ...variants[variant],
      ...(hover && !disabled ? variant === "primary" ? {
        background: "var(--brand-strong)"
      } : {
        background: "var(--green-050)"
      } : {}),
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Single-line text input with optional label and helper/error text. */
function Input({
  label,
  helper,
  error,
  style,
  inputStyle,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "6px",
      fontFamily: "var(--font-body)",
      ...style
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: "var(--weight-bold)",
      color: "var(--text-heading)"
    }
  }, label), /*#__PURE__*/React.createElement("input", _extends({
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false),
    style: {
      fontFamily: "var(--font-body)",
      fontSize: "var(--text-md)",
      padding: "10px 14px",
      borderRadius: "var(--radius-md)",
      border: `1px solid ${error ? "var(--state-danger)" : focus ? "var(--border-brand)" : "var(--border-default)"}`,
      outline: "none",
      color: "var(--text-body)",
      background: "var(--white)",
      boxShadow: focus ? "var(--focus-ring)" : "none",
      transition: "box-shadow var(--duration-fast) var(--ease-out)",
      ...inputStyle
    }
  }, rest)), (error || helper) && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      color: error ? "var(--state-danger)" : "var(--text-muted)"
    }
  }, error || helper));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Radio.jsx
try { (() => {
/** Radio group. options: [{value, label}]. Controlled via value/onChange or uncontrolled. */
function Radio({
  name,
  options = [],
  value,
  defaultValue,
  onChange,
  disabled = false,
  direction = "column",
  style
}) {
  const [internal, setInternal] = React.useState(defaultValue);
  const current = value !== undefined ? value : internal;
  const pick = v => {
    if (value === undefined) setInternal(v);
    onChange && onChange(v);
  };
  return /*#__PURE__*/React.createElement("div", {
    role: "radiogroup",
    style: {
      display: "flex",
      flexDirection: direction,
      gap: direction === "row" ? "20px" : "10px",
      fontFamily: "var(--font-body)",
      ...style
    }
  }, options.map(o => {
    const on = current === o.value;
    return /*#__PURE__*/React.createElement("label", {
      key: o.value,
      style: {
        display: "inline-flex",
        alignItems: "center",
        gap: "10px",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.45 : 1
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        position: "relative",
        width: 20,
        height: 20,
        flex: "none"
      }
    }, /*#__PURE__*/React.createElement("input", {
      type: "radio",
      name: name,
      checked: on,
      onChange: () => pick(o.value),
      disabled: disabled,
      style: {
        position: "absolute",
        inset: 0,
        opacity: 0,
        margin: 0,
        cursor: "inherit"
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        position: "absolute",
        inset: 0,
        borderRadius: "50%",
        border: `1.5px solid ${on ? "var(--brand)" : "var(--border-default)"}`,
        background: "var(--white)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center"
      }
    }, on && /*#__PURE__*/React.createElement("span", {
      style: {
        width: 10,
        height: 10,
        borderRadius: "50%",
        background: "var(--brand)"
      }
    }))), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: "var(--text-md)",
        color: "var(--text-body)"
      }
    }, o.label));
  }));
}
Object.assign(__ds_scope, { Radio });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Radio.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Native select styled to match Input. options: [{value, label}] */
function Select({
  label,
  options = [],
  style,
  selectStyle,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "6px",
      fontFamily: "var(--font-body)",
      ...style
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: "var(--weight-bold)",
      color: "var(--text-heading)"
    }
  }, label), /*#__PURE__*/React.createElement("select", _extends({
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false),
    style: {
      fontFamily: "var(--font-body)",
      fontSize: "var(--text-md)",
      padding: "10px 14px",
      borderRadius: "var(--radius-md)",
      border: `1px solid ${focus ? "var(--border-brand)" : "var(--border-default)"}`,
      outline: "none",
      color: "var(--text-body)",
      background: "var(--white)",
      boxShadow: focus ? "var(--focus-ring)" : "none",
      appearance: "none",
      backgroundImage: "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'><path d='M1 1l5 5 5-5' fill='none' stroke='%235C6B62' stroke-width='2' stroke-linecap='round'/></svg>\")",
      backgroundRepeat: "no-repeat",
      backgroundPosition: "right 14px center",
      ...selectStyle
    }
  }, rest), options.map(o => /*#__PURE__*/React.createElement("option", {
    key: o.value,
    value: o.value
  }, o.label))));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
/** Toggle switch. Controlled via checked/onChange or uncontrolled. */
function Switch({
  label,
  checked,
  defaultChecked,
  onChange,
  disabled = false,
  style
}) {
  const [internal, setInternal] = React.useState(!!defaultChecked);
  const isOn = checked !== undefined ? checked : internal;
  const toggle = () => {
    if (disabled) return;
    if (checked === undefined) setInternal(!isOn);
    onChange && onChange(!isOn);
  };
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "10px",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.45 : 1,
      fontFamily: "var(--font-body)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("button", {
    role: "switch",
    "aria-checked": isOn,
    onClick: toggle,
    disabled: disabled,
    style: {
      width: 44,
      height: 26,
      borderRadius: "var(--radius-pill)",
      border: "none",
      padding: 3,
      background: isOn ? "var(--brand)" : "var(--ink-300)",
      transition: "background var(--duration-base) var(--ease-out)",
      cursor: "inherit",
      display: "flex",
      flex: "none"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 20,
      height: 20,
      borderRadius: "50%",
      background: "var(--white)",
      boxShadow: "var(--shadow-sm)",
      transform: isOn ? "translateX(18px)" : "translateX(0)",
      transition: "transform var(--duration-base) var(--ease-out)"
    }
  })), label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-md)",
      color: "var(--text-body)"
    }
  }, label));
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// components/surfaces/Badge.jsx
try { (() => {
/** Small status badge. tones: brand | neutral | success | warning | danger | sky */
function Badge({
  tone = "brand",
  children,
  style
}) {
  const tones = {
    brand: {
      background: "var(--green-100)",
      color: "var(--green-800)"
    },
    neutral: {
      background: "var(--ink-100)",
      color: "var(--ink-700)"
    },
    success: {
      background: "var(--green-100)",
      color: "var(--green-700)"
    },
    warning: {
      background: "var(--amber-100)",
      color: "var(--amber-600)"
    },
    danger: {
      background: "var(--red-100)",
      color: "var(--red-600)"
    },
    sky: {
      background: "var(--sky-100)",
      color: "var(--sky-600)"
    }
  };
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      padding: "3px 10px",
      borderRadius: "var(--radius-pill)",
      fontFamily: "var(--font-body)",
      fontSize: "var(--text-xs)",
      fontWeight: "var(--weight-bold)",
      letterSpacing: "0.02em",
      ...tones[tone],
      ...style
    }
  }, children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/surfaces/Badge.jsx", error: String((e && e.message) || e) }); }

// components/surfaces/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Content card. variants: default (white, shadow) | subtle (mist green) | deep (dark green, inverted text) */
function Card({
  variant = "default",
  padding = "var(--space-5)",
  children,
  style,
  ...rest
}) {
  const variants = {
    default: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-subtle)",
      boxShadow: "var(--shadow-card)",
      color: "var(--text-body)"
    },
    subtle: {
      background: "var(--surface-subtle)",
      border: "1px solid var(--green-100)",
      color: "var(--text-body)"
    },
    deep: {
      background: "var(--surface-deep)",
      border: "none",
      color: "var(--white)"
    }
  };
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      borderRadius: "var(--radius-lg)",
      padding,
      fontFamily: "var(--font-body)",
      ...variants[variant],
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/surfaces/Card.jsx", error: String((e && e.message) || e) }); }

// components/surfaces/Tabs.jsx
try { (() => {
/** Underline tabs. tabs: [{id, label}]. Controlled via active/onChange or uncontrolled. */
function Tabs({
  tabs = [],
  active,
  defaultActive,
  onChange,
  style
}) {
  const [internal, setInternal] = React.useState(defaultActive || tabs[0] && tabs[0].id);
  const current = active !== undefined ? active : internal;
  const pick = id => {
    if (active === undefined) setInternal(id);
    onChange && onChange(id);
  };
  return /*#__PURE__*/React.createElement("div", {
    role: "tablist",
    style: {
      display: "flex",
      gap: "4px",
      borderBottom: "1px solid var(--border-subtle)",
      fontFamily: "var(--font-body)",
      ...style
    }
  }, tabs.map(t => {
    const on = current === t.id;
    return /*#__PURE__*/React.createElement("button", {
      key: t.id,
      role: "tab",
      "aria-selected": on,
      onClick: () => pick(t.id),
      style: {
        border: "none",
        background: "transparent",
        cursor: "pointer",
        padding: "10px 16px",
        fontFamily: "var(--font-body)",
        fontSize: "var(--text-md)",
        color: on ? "var(--brand-strong)" : "var(--text-muted)",
        fontWeight: on ? "var(--weight-bold)" : "var(--weight-regular)",
        borderBottom: `2px solid ${on ? "var(--brand)" : "transparent"}`,
        marginBottom: "-1px",
        transition: "color var(--duration-fast) var(--ease-out)"
      }
    }, t.label);
  }));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/surfaces/Tabs.jsx", error: String((e && e.message) || e) }); }

// components/surfaces/Tag.jsx
try { (() => {
/** Removable tag/chip. Pass onRemove to show the × affordance. */
function Tag({
  children,
  onRemove,
  style
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "6px",
      padding: "5px 12px",
      borderRadius: "var(--radius-pill)",
      border: "1px solid var(--border-default)",
      background: "var(--white)",
      fontFamily: "var(--font-body)",
      fontSize: "var(--text-sm)",
      color: "var(--text-body)",
      ...style
    }
  }, children, onRemove && /*#__PURE__*/React.createElement("button", {
    onClick: onRemove,
    "aria-label": "Remove",
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      border: "none",
      background: hover ? "var(--ink-100)" : "transparent",
      borderRadius: "50%",
      width: 16,
      height: 16,
      padding: 0,
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      color: "var(--text-muted)",
      fontSize: "12px",
      lineHeight: 1
    }
  }, "\xD7"));
}
Object.assign(__ds_scope, { Tag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/surfaces/Tag.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Dialog = __ds_scope.Dialog;

__ds_ns.Toast = __ds_scope.Toast;

__ds_ns.Tooltip = __ds_scope.Tooltip;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Checkbox = __ds_scope.Checkbox;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Radio = __ds_scope.Radio;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Switch = __ds_scope.Switch;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Tabs = __ds_scope.Tabs;

__ds_ns.Tag = __ds_scope.Tag;

})();
