; === Annotated SMT2 Model ===
(set-logic ALL)
; Mixing_of_Liquids [Mixing_of_Liquids001] -> resource: HC10  (Capabilities: —)
(declare-fun assign_Mixing_of_Liquids001_resource_HC10 () Bool)
; Mixing_of_Liquids [Mixing_of_Liquids001] -> resource: HC20  (Capabilities: StirringDuration, StirringPulseContinuous, StirringPulseDuration)
(declare-fun assign_Mixing_of_Liquids001_resource_HC20 () Bool)
; Mixing_of_Liquids [Mixing_of_Liquids001] -> resource: HC30  (Capabilities: StirringDuration)
(declare-fun assign_Mixing_of_Liquids001_resource_HC30 () Bool)
; Dosing [Dosing001] -> resource: HC10  (Capabilities: Dosing)
(declare-fun assign_Dosing001_resource_HC10 () Bool)
; Dosing [Dosing001] -> resource: HC20  (Capabilities: Dosing)
(declare-fun assign_Dosing001_resource_HC20 () Bool)
; Dosing [Dosing001] -> resource: HC30  (Capabilities: —)
(declare-fun assign_Dosing001_resource_HC30 () Bool)
; Heating_of_liquids [Heating_of_liquids001] -> resource: HC10  (Capabilities: HeatingControlled, HeatingPWM, HeatingRamp)
(declare-fun assign_Heating_of_liquids001_resource_HC10 () Bool)
; Heating_of_liquids [Heating_of_liquids001] -> resource: HC20  (Capabilities: —)
(declare-fun assign_Heating_of_liquids001_resource_HC20 () Bool)
; Heating_of_liquids [Heating_of_liquids001] -> resource: HC30  (Capabilities: —)
(declare-fun assign_Heating_of_liquids001_resource_HC30 () Bool)

; Excluded assignments due to failed preconditions or property mismatch
(assert (! (not assign_Dosing001_resource_HC30) :named precond_fail_Dosing001_resource HC30))
(assert (! (not assign_Heating_of_liquids001_resource_HC30) :named precond_fail_Heating_of_liquids001_resource HC30))
(assert (! (not assign_Heating_of_liquids001_resource_HC20) :named precond_fail_Heating_of_liquids001_resource HC20))
(assert (! (not assign_Mixing_of_Liquids001_resource_HC10) :named precond_fail_Mixing_of_Liquids001_resource HC10))

; Postprocessed negations
(assert (! (not assign_Dosing001_resource_HC10) :named postproc_neg_assign_Dosing001_resource_HC10))
(assert (! (not assign_Mixing_of_Liquids001_resource_HC30) :named postproc_neg_assign_Mixing_of_Liquids001_resource_HC30))

; Step: Mixing_of_Liquids [Mixing_of_Liquids001]: Must be mapped to exactly one resource
(assert (! (= (+ (ite assign_Mixing_of_Liquids001_resource_HC10 1 0) (ite assign_Mixing_of_Liquids001_resource_HC20 1 0) (ite assign_Mixing_of_Liquids001_resource_HC30 1 0)) 1) :named assign_unique_Mixing_of_Liquids001))
; Step: Dosing [Dosing001]: Must be mapped to exactly one resource
(assert (! (= (+ (ite assign_Dosing001_resource_HC10 1 0) (ite assign_Dosing001_resource_HC20 1 0) (ite assign_Dosing001_resource_HC30 1 0)) 1) :named assign_unique_Dosing001))
; Step: Heating_of_liquids [Heating_of_liquids001]: Must be mapped to exactly one resource
(assert (! (= (+ (ite assign_Heating_of_liquids001_resource_HC10 1 0) (ite assign_Heating_of_liquids001_resource_HC20 1 0) (ite assign_Heating_of_liquids001_resource_HC30 1 0)) 1) :named assign_unique_Heating_of_liquids001))

(check-sat)
