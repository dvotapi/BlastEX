-- DROP SCHEMA public;

CREATE SCHEMA public AUTHORIZATION user1;

COMMENT ON SCHEMA public IS 'standard public schema';

-- DROP TYPE public."container_material";

CREATE TYPE public."container_material" AS ENUM (
	'Гофрокартон',
	'ДВП',
	'Дерево',
	'Полиэтилен');

-- DROP TYPE public."contract_direction";

CREATE TYPE public."contract_direction" AS ENUM (
	'Клиентский',
	'Поставщик',
	'Внутренний');

-- DROP TYPE public."drilling_work_type";

CREATE TYPE public."drilling_work_type" AS ENUM (
	'Первичное бурение',
	'Перебур',
	'Прочистка',
	'ТО',
	'Ремонт',
	'Подготовка площадки',
	'Разметка блока',
	'Ожидание топлива');

-- DROP TYPE public."packaging_method";

CREATE TYPE public."packaging_method" AS ENUM (
	'Бухта',
	'Катушка',
	'Патрон',
	'Насыпью');

-- DROP TYPE public."work_type";

CREATE TYPE public."work_type" AS ENUM (
	'Буровые работы',
	'Взрывные работы',
	'Поставка взрывчатых веществ',
	'Транспортные услуги',
	'Прочее',
	'Техническое обслуживание',
	'Ремонт');

-- DROP SEQUENCE public.bank_accounts_id_seq;

CREATE SEQUENCE public.bank_accounts_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.contract_specifications_id_seq;

CREATE SEQUENCE public.contract_specifications_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.contracts_id_seq;

CREATE SEQUENCE public.contracts_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.counterparties_id_seq;

CREATE SEQUENCE public.counterparties_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.counterparty_bank_accounts_id_seq;

CREATE SEQUENCE public.counterparty_bank_accounts_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.delay_series_id_seq;

CREATE SEQUENCE public.delay_series_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.drilling_downtime_id_seq;

CREATE SEQUENCE public.drilling_downtime_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.drilling_operation_details_id_seq;

CREATE SEQUENCE public.drilling_operation_details_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.drilling_operation_tools_id_seq;

CREATE SEQUENCE public.drilling_operation_tools_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.drilling_operations_id_seq;

CREATE SEQUENCE public.drilling_operations_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.drilling_requests_id_seq;

CREATE SEQUENCE public.drilling_requests_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.employees_id_seq;

CREATE SEQUENCE public.employees_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.equipment_maintenance_id_seq;

CREATE SEQUENCE public.equipment_maintenance_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.equipment_models_id_seq;

CREATE SEQUENCE public.equipment_models_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.equipment_units_id_seq;

CREATE SEQUENCE public.equipment_units_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.explosive_material_prices_id_seq;

CREATE SEQUENCE public.explosive_material_prices_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.explosive_purchase_specs_id_seq;

CREATE SEQUENCE public.explosive_purchase_specs_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.explosive_spec_items_id_seq;

CREATE SEQUENCE public.explosive_spec_items_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.fuel_suppliers_id_seq;

CREATE SEQUENCE public.fuel_suppliers_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.initiating_device_types_id_seq;

CREATE SEQUENCE public.initiating_device_types_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.machine_types_id_seq;

CREATE SEQUENCE public.machine_types_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.manufacturers_id_seq;

CREATE SEQUENCE public.manufacturers_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.packaging_containers_id_seq;

CREATE SEQUENCE public.packaging_containers_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.packaging_specifications_id_seq;

CREATE SEQUENCE public.packaging_specifications_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.service_prices_id_seq;

CREATE SEQUENCE public.service_prices_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.sites_id_seq;

CREATE SEQUENCE public.sites_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.tool_assignments_id_seq;

CREATE SEQUENCE public.tool_assignments_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.tool_transactions_id_seq;

CREATE SEQUENCE public.tool_transactions_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.tool_types_id_seq;

CREATE SEQUENCE public.tool_types_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.tools_inventory_id_seq;

CREATE SEQUENCE public.tools_inventory_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;-- public.counterparties определение

-- Drop table

-- DROP TABLE public.counterparties;

CREATE TABLE public.counterparties ( id int4 GENERATED BY DEFAULT AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, full_name text NOT NULL, short_name text NULL, inn varchar(12) NOT NULL, kpp varchar(9) NULL, legal_address text NULL, contact_person text NULL, phone text NULL, email text NULL, is_client bool DEFAULT true NULL, is_supplier bool DEFAULT false NULL, is_active bool DEFAULT true NULL, created_at timestamptz DEFAULT now() NULL, ogrn varchar(15) NULL, postal_address text NULL, director_name text NULL, director_title text NULL, bank_name text NULL, bik varchar(9) NULL, settlement_account varchar(20) NULL, correspondent_account varchar(20) NULL, source_filename text NULL, source_text text NULL, extraction_warnings jsonb DEFAULT '[]'::jsonb NOT NULL, updated_at timestamptz DEFAULT now() NOT NULL, CONSTRAINT counterparties_bik_format CHECK (((bik IS NULL) OR ((bik)::text ~ '^[0-9]{9}$'::text))) NOT VALID, CONSTRAINT counterparties_correspondent_account_format CHECK (((correspondent_account IS NULL) OR ((correspondent_account)::text ~ '^[0-9]{20}$'::text))) NOT VALID, CONSTRAINT counterparties_inn_format CHECK (((inn)::text ~ '^[0-9]{10}([0-9]{2})?$'::text)) NOT VALID, CONSTRAINT counterparties_inn_key UNIQUE (inn), CONSTRAINT counterparties_kpp_format CHECK (((kpp IS NULL) OR ((kpp)::text ~ '^[0-9]{9}$'::text))) NOT VALID, CONSTRAINT counterparties_ogrn_format CHECK (((ogrn IS NULL) OR ((ogrn)::text ~ '^[0-9]{13}([0-9]{2})?$'::text))) NOT VALID, CONSTRAINT counterparties_pkey PRIMARY KEY (id), CONSTRAINT counterparties_settlement_account_format CHECK (((settlement_account IS NULL) OR ((settlement_account)::text ~ '^[0-9]{20}$'::text))) NOT VALID);
ALTER TABLE public.counterparties ENABLE ROW LEVEL SECURITY;


-- public.employees определение

-- Drop table

-- DROP TABLE public.employees;

CREATE TABLE public.employees ( id serial4 NOT NULL, last_name text NOT NULL, first_name text NOT NULL, middle_name text NULL, email text NULL, phone text NULL, personnel_number text NULL, "position" text DEFAULT 'Машинист БУ'::text NULL, inn varchar(12) NULL, snils varchar(14) NULL, passport_series varchar(4) NULL, passport_number varchar(6) NULL, passport_issued_by text NULL, passport_date_issued date NULL, is_active bool DEFAULT true NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT employees_email_key UNIQUE (email), CONSTRAINT employees_inn_key UNIQUE (inn), CONSTRAINT employees_personnel_number_key UNIQUE (personnel_number), CONSTRAINT employees_pkey PRIMARY KEY (id), CONSTRAINT employees_snils_key UNIQUE (snils));
ALTER TABLE public.employees ENABLE ROW LEVEL SECURITY;


-- public.fuel_suppliers определение

-- Drop table

-- DROP TABLE public.fuel_suppliers;

CREATE TABLE public.fuel_suppliers ( id serial4 NOT NULL, "name" text NOT NULL, contract_number text NULL, is_active bool DEFAULT true NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT fuel_suppliers_name_key UNIQUE (name), CONSTRAINT fuel_suppliers_pkey PRIMARY KEY (id));
ALTER TABLE public.fuel_suppliers ENABLE ROW LEVEL SECURITY;


-- public.machine_types определение

-- Drop table

-- DROP TABLE public.machine_types;

CREATE TABLE public.machine_types ( id serial4 NOT NULL, "name" text NOT NULL, description text NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT machine_types_name_key UNIQUE (name), CONSTRAINT machine_types_pkey PRIMARY KEY (id));
COMMENT ON TABLE public.machine_types IS 'Справочник категорий техники (Буровая установка, СЗМ, экскаватор, машина для перевозки)';
ALTER TABLE public.machine_types ENABLE ROW LEVEL SECURITY;


-- public.manufacturers определение

-- Drop table

-- DROP TABLE public.manufacturers;

CREATE TABLE public.manufacturers ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, "name" text NOT NULL, short_name varchar(50) NULL, legal_address text NULL, is_active bool DEFAULT true NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT manufacturers_pkey PRIMARY KEY (id));
ALTER TABLE public.manufacturers ENABLE ROW LEVEL SECURITY;


-- public.packaging_containers определение

-- Drop table

-- DROP TABLE public.packaging_containers;

CREATE TABLE public.packaging_containers ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, material public."container_material" NOT NULL, dimensions text NULL, weight_empty_kg numeric(5, 2) NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT packaging_containers_pkey PRIMARY KEY (id));
ALTER TABLE public.packaging_containers ENABLE ROW LEVEL SECURITY;


-- public.sites определение

-- Drop table

-- DROP TABLE public.sites;

CREATE TABLE public.sites ( id serial4 NOT NULL, full_name text NOT NULL, short_name varchar(5) NULL, client_legal_name text NOT NULL, mineral_type text NULL, is_active bool DEFAULT true NULL, created_at timestamptz DEFAULT now() NULL, updated_at timestamptz DEFAULT now() NULL, CONSTRAINT sites_pkey PRIMARY KEY (id));
ALTER TABLE public.sites ENABLE ROW LEVEL SECURITY;


-- public.tool_types определение

-- Drop table

-- DROP TABLE public.tool_types;

CREATE TABLE public.tool_types ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, "name" text NOT NULL, expected_lifetime_meters numeric NULL, description text NULL, diameter numeric NULL, thread_type text NULL, CONSTRAINT tool_types_pkey PRIMARY KEY (id));
ALTER TABLE public.tool_types ENABLE ROW LEVEL SECURITY;


-- public.bank_accounts определение

-- Drop table

-- DROP TABLE public.bank_accounts;

CREATE TABLE public.bank_accounts ( id int4 GENERATED BY DEFAULT AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, counterparty_id int4 NULL, bank_name text NOT NULL, bik varchar(9) NOT NULL, account_number varchar(20) NOT NULL, is_primary bool DEFAULT false NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT bank_accounts_pkey PRIMARY KEY (id), CONSTRAINT bank_accounts_counterparty_id_fkey FOREIGN KEY (counterparty_id) REFERENCES public.counterparties(id) ON DELETE CASCADE);
ALTER TABLE public.bank_accounts ENABLE ROW LEVEL SECURITY;


-- public.contracts определение

-- Drop table

-- DROP TABLE public.contracts;

CREATE TABLE public.contracts ( id int4 GENERATED BY DEFAULT AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, counterparty_id int4 NOT NULL, direction public."contract_direction" DEFAULT 'Клиентский'::contract_direction NOT NULL, contract_number text NOT NULL, contract_date date NOT NULL, site_id int4 NULL, valid_from date NULL, valid_to date NULL, is_active bool DEFAULT true NULL, created_at timestamptz DEFAULT now() NULL, created_by uuid NULL, CONSTRAINT contracts_pkey PRIMARY KEY (id), CONSTRAINT contracts_counterparty_id_fkey FOREIGN KEY (counterparty_id) REFERENCES public.counterparties(id), CONSTRAINT contracts_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.sites(id));
ALTER TABLE public.contracts ENABLE ROW LEVEL SECURITY;


-- public.counterparty_bank_accounts определение

-- Drop table

-- DROP TABLE public.counterparty_bank_accounts;

CREATE TABLE public.counterparty_bank_accounts ( id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL, counterparty_id int4 NOT NULL, bank_name text NOT NULL, bik varchar(9) NULL, settlement_account varchar(20) NOT NULL, correspondent_account varchar(20) NULL, is_primary bool DEFAULT false NOT NULL, created_at timestamptz DEFAULT now() NOT NULL, updated_at timestamptz DEFAULT now() NOT NULL, CONSTRAINT counterparty_bank_accounts_bik_format CHECK (((bik IS NULL) OR ((bik)::text ~ '^[0-9]{9}$'::text))), CONSTRAINT counterparty_bank_accounts_counterparty_rs_key UNIQUE (counterparty_id, settlement_account), CONSTRAINT counterparty_bank_accounts_ks_format CHECK (((correspondent_account IS NULL) OR ((correspondent_account)::text ~ '^[0-9]{20}$'::text))), CONSTRAINT counterparty_bank_accounts_pkey PRIMARY KEY (id), CONSTRAINT counterparty_bank_accounts_rs_format CHECK (((settlement_account)::text ~ '^[0-9]{20}$'::text)), CONSTRAINT counterparty_bank_accounts_counterparty_id_fkey FOREIGN KEY (counterparty_id) REFERENCES public.counterparties(id) ON DELETE CASCADE);
CREATE INDEX counterparty_bank_accounts_counterparty_idx ON public.counterparty_bank_accounts USING btree (counterparty_id);
ALTER TABLE public.counterparty_bank_accounts ENABLE ROW LEVEL SECURITY;


-- public.drilling_requests определение

-- Drop table

-- DROP TABLE public.drilling_requests;

CREATE TABLE public.drilling_requests ( id serial4 NOT NULL, contract_id int4 NULL, site_id int4 NULL, block_num text NOT NULL, planned_meters numeric(10, 2) NOT NULL, horizon text NULL, diameter_mm numeric NULL, deadline date NULL, created_at timestamptz DEFAULT now() NULL, holes_count int4 NULL, CONSTRAINT drilling_requests_pkey PRIMARY KEY (id), CONSTRAINT drilling_requests_contract_id_fkey FOREIGN KEY (contract_id) REFERENCES public.contracts(id), CONSTRAINT drilling_requests_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.sites(id));

-- Column comments

COMMENT ON COLUMN public.drilling_requests.holes_count IS 'Запланированное количество скважин на блоке';
ALTER TABLE public.drilling_requests ENABLE ROW LEVEL SECURITY;


-- public.equipment_models определение

-- Drop table

-- DROP TABLE public.equipment_models;

CREATE TABLE public.equipment_models ( id serial4 NOT NULL, machine_type_id int4 NULL, brand varchar(128) NOT NULL, model_name varchar(128) NOT NULL, engine_brand varchar(128) NULL, engine_model varchar(128) NULL, engine_power_kw numeric(10, 2) NULL, weight_t numeric(10, 2) NULL, length_m numeric(10, 2) NULL, width_m numeric(10, 2) NULL, height_m numeric(10, 2) NULL, wheeled bool DEFAULT false NULL, created_at timestamptz DEFAULT now() NULL, updated_at timestamptz DEFAULT now() NULL, CONSTRAINT equipment_models_model_name_key UNIQUE (model_name), CONSTRAINT equipment_models_pkey PRIMARY KEY (id), CONSTRAINT equipment_models_machine_type_id_fkey FOREIGN KEY (machine_type_id) REFERENCES public.machine_types(id));
CREATE INDEX idx_equipment_models_name ON public.equipment_models USING btree (model_name);
COMMENT ON TABLE public.equipment_models IS 'Технические паспорта моделей техники (шаблоны для ТО)';


-- public.equipment_units определение

-- Drop table

-- DROP TABLE public.equipment_units;

CREATE TABLE public.equipment_units ( id serial4 NOT NULL, model_id int4 NOT NULL, internal_id varchar(64) NOT NULL, serial_number varchar(128) NULL, current_hours numeric(12, 2) DEFAULT 0 NULL, current_km numeric(12, 2) DEFAULT 0 NULL, status text DEFAULT 'В работе'::text NULL, current_site_id int4 NULL, created_at timestamptz DEFAULT now() NULL, updated_at timestamptz DEFAULT now() NULL, CONSTRAINT equipment_units_internal_id_key UNIQUE (internal_id), CONSTRAINT equipment_units_pkey PRIMARY KEY (id), CONSTRAINT status_check CHECK ((status = ANY (ARRAY['В работе'::text, 'На ТО'::text, 'Ремонт'::text, 'Списано'::text]))), CONSTRAINT equipment_units_current_site_id_fkey FOREIGN KEY (current_site_id) REFERENCES public.sites(id), CONSTRAINT equipment_units_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.equipment_models(id));
CREATE INDEX idx_units_internal_id ON public.equipment_units USING btree (internal_id);
COMMENT ON TABLE public.equipment_units IS 'Реестр конкретных единиц техники и их текущего состояния';


-- public.explosive_purchase_specs определение

-- Drop table

-- DROP TABLE public.explosive_purchase_specs;

CREATE TABLE public.explosive_purchase_specs ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, contract_id int4 NULL, spec_number text NOT NULL, spec_date date NOT NULL, delivery_period text NULL, total_delivery_cost_no_vat numeric(15, 2) NULL, vat_rate numeric DEFAULT 22.0 NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT explosive_purchase_specs_pkey PRIMARY KEY (id), CONSTRAINT explosive_purchase_specs_contract_id_fkey FOREIGN KEY (contract_id) REFERENCES public.contracts(id));


-- public.initiating_device_types определение

-- Drop table

-- DROP TABLE public.initiating_device_types;

CREATE TABLE public.initiating_device_types ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, "name" text NOT NULL, danger_class varchar(10) NULL, un_number_standard varchar(10) NULL, un_number_protected varchar(10) NULL, shelf_life_years numeric(3, 1) NULL, core_mass_gm numeric(5, 2) NULL, bam_certification text NULL, description text NULL, created_at timestamptz DEFAULT now() NULL, manufacturer_id int4 NULL, CONSTRAINT initiating_device_types_pkey PRIMARY KEY (id), CONSTRAINT initiating_device_types_manufacturer_id_fkey FOREIGN KEY (manufacturer_id) REFERENCES public.manufacturers(id));
ALTER TABLE public.initiating_device_types ENABLE ROW LEVEL SECURITY;


-- public.packaging_specifications определение

-- Drop table

-- DROP TABLE public.packaging_specifications;

CREATE TABLE public.packaging_specifications ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, device_type_id int4 NULL, container_id int4 NULL, pack_method public."packaging_method" DEFAULT 'Бухта'::packaging_method NULL, length_min numeric(6, 2) NOT NULL, length_max numeric(6, 2) NOT NULL, units_per_box int4 NOT NULL, total_length_in_box_m numeric NULL, weight_net_min numeric(10, 2) NULL, weight_net_max numeric(10, 2) NULL, weight_gross_min numeric(10, 2) NULL, weight_gross_max numeric(10, 2) NULL, CONSTRAINT length_range_check CHECK ((length_max >= length_min)), CONSTRAINT packaging_specifications_pkey PRIMARY KEY (id), CONSTRAINT packaging_specifications_container_id_fkey FOREIGN KEY (container_id) REFERENCES public.packaging_containers(id), CONSTRAINT packaging_specifications_device_type_id_fkey FOREIGN KEY (device_type_id) REFERENCES public.initiating_device_types(id));
ALTER TABLE public.packaging_specifications ENABLE ROW LEVEL SECURITY;


-- public.service_prices определение

-- Drop table

-- DROP TABLE public.service_prices;

CREATE TABLE public.service_prices ( id serial4 NOT NULL, site_id int4 NULL, service_name text DEFAULT 'Бурение скважин'::text NULL, price_per_meter numeric(10, 2) NOT NULL, is_active bool DEFAULT true NULL, valid_from date DEFAULT CURRENT_DATE NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT service_prices_pkey PRIMARY KEY (id), CONSTRAINT service_prices_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.sites(id));
ALTER TABLE public.service_prices ENABLE ROW LEVEL SECURITY;


-- public.tools_inventory определение

-- Drop table

-- DROP TABLE public.tools_inventory;

CREATE TABLE public.tools_inventory ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, tool_type_id int4 NULL, serial_number text NOT NULL, brand text NULL, model text NULL, status text DEFAULT 'Склад'::text NULL, current_site_id int4 NULL, current_rig_id int4 NULL, total_meters_drilled numeric DEFAULT 0 NULL, is_active bool DEFAULT true NULL, created_at timestamptz DEFAULT now() NULL, purchase_price numeric NULL, purchase_date date NULL, supplier_id int4 NULL, CONSTRAINT tools_inventory_pkey PRIMARY KEY (id), CONSTRAINT tools_inventory_serial_number_key UNIQUE (serial_number), CONSTRAINT tools_inventory_status_check CHECK ((status = ANY (ARRAY['Склад'::text, 'В работе'::text, 'Списано'::text, 'Ремонт'::text]))), CONSTRAINT tools_inventory_current_site_id_fkey FOREIGN KEY (current_site_id) REFERENCES public.sites(id), CONSTRAINT tools_inventory_current_unit_id_fkey FOREIGN KEY (current_rig_id) REFERENCES public.equipment_units(id) ON DELETE SET NULL, CONSTRAINT tools_inventory_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.counterparties(id), CONSTRAINT tools_inventory_tool_type_id_fkey FOREIGN KEY (tool_type_id) REFERENCES public.tool_types(id));
ALTER TABLE public.tools_inventory ENABLE ROW LEVEL SECURITY;


-- public.contract_specifications определение

-- Drop table

-- DROP TABLE public.contract_specifications;

CREATE TABLE public.contract_specifications ( id int4 GENERATED BY DEFAULT AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, contract_id int4 NOT NULL, service_type public."work_type" NOT NULL, service_name text NOT NULL, price_per_unit numeric NOT NULL, unit text DEFAULT 'пог. м'::text NOT NULL, is_active bool DEFAULT true NULL, base_fuel_price numeric DEFAULT 75115 NULL, fuel_threshold_pct numeric DEFAULT 5 NULL, fuel_component_weight numeric DEFAULT 0.3 NULL, CONSTRAINT contract_specifications_pkey PRIMARY KEY (id), CONSTRAINT contract_specifications_contract_id_fkey FOREIGN KEY (contract_id) REFERENCES public.contracts(id) ON DELETE CASCADE);
ALTER TABLE public.contract_specifications ENABLE ROW LEVEL SECURITY;


-- public.delay_series определение

-- Drop table

-- DROP TABLE public.delay_series;

CREATE TABLE public.delay_series ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, device_type_id int4 NULL, delay_ms int4 NOT NULL, color_mark text NULL, is_standard bool DEFAULT true NULL, description text NULL, CONSTRAINT delay_series_pkey PRIMARY KEY (id), CONSTRAINT delay_series_device_type_id_fkey FOREIGN KEY (device_type_id) REFERENCES public.initiating_device_types(id));
ALTER TABLE public.delay_series ENABLE ROW LEVEL SECURITY;


-- public.drilling_operations определение

-- Drop table

-- DROP TABLE public.drilling_operations;

CREATE TABLE public.drilling_operations ( id serial4 NOT NULL, work_date date NOT NULL, shift text NULL, site_id int4 NULL, operator_id int4 NULL, rig_id int4 NULL, holes_count int4 DEFAULT 0 NOT NULL, meters_drilled numeric(10, 2) DEFAULT 0 NOT NULL, engine_hours_end numeric(10, 1) NOT NULL, fuel_added numeric(10, 1) DEFAULT 0 NULL, fuel_supplier_id int4 NULL, created_at timestamptz DEFAULT now() NULL, block_num text NULL, CONSTRAINT drilling_operations_pkey PRIMARY KEY (id), CONSTRAINT drilling_operations_shift_check CHECK ((shift = ANY (ARRAY['Д'::text, 'Н'::text]))), CONSTRAINT drilling_operations_fuel_supplier_id_fkey FOREIGN KEY (fuel_supplier_id) REFERENCES public.fuel_suppliers(id), CONSTRAINT drilling_operations_operator_id_fkey FOREIGN KEY (operator_id) REFERENCES public.employees(id), CONSTRAINT drilling_operations_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.sites(id), CONSTRAINT drilling_operations_unit_id_fkey FOREIGN KEY (rig_id) REFERENCES public.equipment_units(id));
ALTER TABLE public.drilling_operations ENABLE ROW LEVEL SECURITY;


-- public.equipment_maintenance определение

-- Drop table

-- DROP TABLE public.equipment_maintenance;

CREATE TABLE public.equipment_maintenance ( id serial4 NOT NULL, unit_id int4 NOT NULL, operation_id int4 NULL, maintenance_type varchar(50) NOT NULL, failed_node varchar(100) NULL, start_time timestamp NOT NULL, end_time timestamp NULL, duration_hours numeric(5, 2) GENERATED ALWAYS AS ((EXTRACT(epoch FROM end_time - start_time) / 3600.0)) STORED NULL, work_description text NULL, parts_replaced text NULL, executor_counterparty_id int4 NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT equipment_maintenance_pkey PRIMARY KEY (id), CONSTRAINT fk_maintenance_executor FOREIGN KEY (executor_counterparty_id) REFERENCES public.counterparties(id) ON DELETE SET NULL, CONSTRAINT fk_maintenance_operation FOREIGN KEY (operation_id) REFERENCES public.drilling_operations(id) ON DELETE SET NULL, CONSTRAINT fk_maintenance_unit FOREIGN KEY (unit_id) REFERENCES public.equipment_units(id) ON DELETE CASCADE);


-- public.explosive_material_prices определение

-- Drop table

-- DROP TABLE public.explosive_material_prices;

CREATE TABLE public.explosive_material_prices ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, contract_id int4 NULL, device_type_id int4 NULL, price_per_unit_base numeric(15, 2) NOT NULL, vat_rate numeric(5, 2) DEFAULT 22.0 NULL, unit_name text DEFAULT 'тыс. шт.'::text NULL, unit_conversion_factor numeric DEFAULT 1000 NULL, valid_from date NOT NULL, valid_to date NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT explosive_material_prices_pkey PRIMARY KEY (id), CONSTRAINT explosive_material_prices_contract_id_fkey FOREIGN KEY (contract_id) REFERENCES public.contracts(id), CONSTRAINT explosive_material_prices_device_type_id_fkey FOREIGN KEY (device_type_id) REFERENCES public.initiating_device_types(id));
ALTER TABLE public.explosive_material_prices ENABLE ROW LEVEL SECURITY;


-- public.explosive_spec_items определение

-- Drop table

-- DROP TABLE public.explosive_spec_items;

CREATE TABLE public.explosive_spec_items ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, spec_id int4 NULL, device_type_id int4 NULL, quantity_ordered numeric NOT NULL, unit_name text DEFAULT 'тыс. шт.'::text NULL, price_per_unit_no_vat numeric(15, 2) NOT NULL, conversion_factor numeric DEFAULT 1000 NULL, CONSTRAINT explosive_spec_items_pkey PRIMARY KEY (id), CONSTRAINT explosive_spec_items_device_type_id_fkey FOREIGN KEY (device_type_id) REFERENCES public.initiating_device_types(id), CONSTRAINT explosive_spec_items_spec_id_fkey FOREIGN KEY (spec_id) REFERENCES public.explosive_purchase_specs(id) ON DELETE CASCADE);


-- public.tool_assignments определение

-- Drop table

-- DROP TABLE public.tool_assignments;

CREATE TABLE public.tool_assignments ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, tool_id int4 NULL, rig_id int4 NULL, install_date date NOT NULL, install_engine_hours numeric NULL, removal_date date NULL, removal_engine_hours numeric NULL, removal_reason text NULL, CONSTRAINT tool_assignments_dates_check CHECK ((removal_date >= install_date)), CONSTRAINT tool_assignments_pkey PRIMARY KEY (id), CONSTRAINT tool_assignments_tool_id_fkey FOREIGN KEY (tool_id) REFERENCES public.tools_inventory(id), CONSTRAINT tool_assignments_unit_id_fkey FOREIGN KEY (rig_id) REFERENCES public.equipment_units(id) ON DELETE CASCADE);
ALTER TABLE public.tool_assignments ENABLE ROW LEVEL SECURITY;


-- public.tool_transactions определение

-- Drop table

-- DROP TABLE public.tool_transactions;

CREATE TABLE public.tool_transactions ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, tool_id int4 NOT NULL, transaction_type text NOT NULL, from_site_id int4 NULL, to_site_id int4 NULL, responsible_person_id int4 NULL, transaction_date timestamptz DEFAULT now() NULL, document_number text NULL, "comment" text NULL, CONSTRAINT tool_transactions_pkey PRIMARY KEY (id), CONSTRAINT tool_transactions_transaction_type_check CHECK ((transaction_type = ANY (ARRAY['Приход'::text, 'Выдача'::text, 'Возврат'::text, 'Списание'::text, 'Перемещение'::text]))), CONSTRAINT tool_transactions_from_site_id_fkey FOREIGN KEY (from_site_id) REFERENCES public.sites(id), CONSTRAINT tool_transactions_responsible_person_id_fkey FOREIGN KEY (responsible_person_id) REFERENCES public.employees(id), CONSTRAINT tool_transactions_to_site_id_fkey FOREIGN KEY (to_site_id) REFERENCES public.sites(id), CONSTRAINT tool_transactions_tool_id_fkey FOREIGN KEY (tool_id) REFERENCES public.tools_inventory(id));
ALTER TABLE public.tool_transactions ENABLE ROW LEVEL SECURITY;


-- public.drilling_downtime определение

-- Drop table

-- DROP TABLE public.drilling_downtime;

CREATE TABLE public.drilling_downtime ( id serial4 NOT NULL, operation_id int4 NOT NULL, downtime_reason varchar(100) NOT NULL, start_time timestamp NULL, end_time timestamp NULL, duration_hours numeric(4, 2) NOT NULL, "comment" text NULL, CONSTRAINT drilling_downtime_pkey PRIMARY KEY (id), CONSTRAINT drilling_downtime_operation_id_fkey FOREIGN KEY (operation_id) REFERENCES public.drilling_operations(id) ON DELETE CASCADE);


-- public.drilling_operation_details определение

-- Drop table

-- DROP TABLE public.drilling_operation_details;

CREATE TABLE public.drilling_operation_details ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, operation_id int4 NOT NULL, "work_type" public."drilling_work_type" DEFAULT 'Первичное бурение'::drilling_work_type NOT NULL, meters numeric DEFAULT 0 NOT NULL, holes_count int4 DEFAULT 0 NULL, "comment" text NULL, CONSTRAINT drilling_operation_details_pkey PRIMARY KEY (id), CONSTRAINT drilling_operation_details_operation_id_fkey FOREIGN KEY (operation_id) REFERENCES public.drilling_operations(id) ON DELETE CASCADE);
ALTER TABLE public.drilling_operation_details ENABLE ROW LEVEL SECURITY;


-- public.drilling_operation_tools определение

-- Drop table

-- DROP TABLE public.drilling_operation_tools;

CREATE TABLE public.drilling_operation_tools ( id int4 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE) NOT NULL, operation_id int4 NULL, tool_id int4 NULL, meters_drilled_during_shift numeric NOT NULL, CONSTRAINT drilling_operation_tools_pkey PRIMARY KEY (id), CONSTRAINT drilling_operation_tools_operation_id_fkey FOREIGN KEY (operation_id) REFERENCES public.drilling_operations(id) ON DELETE CASCADE, CONSTRAINT drilling_operation_tools_tool_id_fkey FOREIGN KEY (tool_id) REFERENCES public.tools_inventory(id));
ALTER TABLE public.drilling_operation_tools ENABLE ROW LEVEL SECURITY;


-- public.block_analytics исходный текст

CREATE OR REPLACE VIEW public.block_analytics
AS WITH operations_with_hours AS (
         SELECT ops.site_id,
            ops.block_num,
            ops.meters_drilled,
            ops.holes_count,
            ops.fuel_added,
            ops.engine_hours_end - lag(ops.engine_hours_end) OVER (PARTITION BY ops.rig_id ORDER BY ops.engine_hours_end) AS shift_hours
           FROM drilling_operations ops
          WHERE ops.engine_hours_end IS NOT NULL
        ), aggregated_fact AS (
         SELECT operations_with_hours.site_id,
            operations_with_hours.block_num,
            count(*) AS shifts_count,
            sum(operations_with_hours.holes_count) AS total_holes,
            sum(operations_with_hours.meters_drilled) AS total_meters,
            sum(operations_with_hours.shift_hours) AS total_shift_hours,
            sum(operations_with_hours.fuel_added) AS total_fuel
           FROM operations_with_hours
          GROUP BY operations_with_hours.site_id, operations_with_hours.block_num
        ), aggregated_requests AS (
         SELECT drilling_requests.site_id,
            drilling_requests.block_num,
            sum(drilling_requests.planned_meters) AS planned_meters
           FROM drilling_requests
          GROUP BY drilling_requests.site_id, drilling_requests.block_num
        )
 SELECT s.short_name AS "Объект",
    f.block_num AS "Номер блока",
    r.planned_meters AS "План по заявке (м)",
    f.total_meters AS "Фактически пробурено (м)",
    round(f.total_meters / NULLIF(r.planned_meters, 0::numeric) * 100::numeric, 2) AS "Процент выполнения",
    f.shifts_count AS "Факт смен на блоке",
    f.total_holes AS "Факт скважин",
    round(f.total_shift_hours, 1) AS "Факт м/ч",
    f.total_fuel AS "Заправлено ДТ (л)",
    round(f.total_fuel / NULLIF(f.total_meters, 0::numeric), 2) AS "Средний расход л/м"
   FROM aggregated_fact f
     JOIN sites s ON f.site_id = s.id
     LEFT JOIN aggregated_requests r ON f.site_id = r.site_id AND f.block_num = r.block_num
  ORDER BY s.short_name, f.block_num;


-- public.operator_monthly_stats исходный текст

CREATE OR REPLACE VIEW public.operator_monthly_stats
WITH(security_invoker=on)
AS WITH base_data AS (
         SELECT drilling_operations.operator_id,
            drilling_operations.holes_count,
            drilling_operations.meters_drilled,
            drilling_operations.fuel_added,
            drilling_operations.work_date,
            drilling_operations.rig_id,
            drilling_operations.engine_hours_end,
            lag(drilling_operations.engine_hours_end) OVER (PARTITION BY drilling_operations.rig_id ORDER BY drilling_operations.engine_hours_end) AS engine_hours_start
           FROM drilling_operations
        ), calculations AS (
         SELECT base_data.operator_id,
            base_data.holes_count,
            base_data.meters_drilled,
            base_data.fuel_added,
            base_data.work_date,
            base_data.rig_id,
            base_data.engine_hours_end,
            base_data.engine_hours_start,
            base_data.engine_hours_end - base_data.engine_hours_start AS shift_hours
           FROM base_data
        )
 SELECT (((e.last_name || ' '::text) || "left"(e.first_name, 1)) || '.'::text) ||
        CASE
            WHEN e.middle_name IS NOT NULL THEN "left"(e.middle_name, 1) || '.'::text
            ELSE ''::text
        END AS operator_fio,
    count(*) AS shifts_worked,
    sum(c.holes_count) AS total_holes,
    sum(c.meters_drilled) AS total_meters,
    sum(
        CASE
            WHEN c.shift_hours > 0::numeric THEN c.shift_hours
            ELSE 0::numeric
        END) AS total_engine_hours,
    round(sum(c.meters_drilled) / NULLIF(sum(
        CASE
            WHEN c.shift_hours > 0::numeric THEN c.shift_hours
            ELSE 0::numeric
        END), 0::numeric), 2) AS meters_per_hour,
    sum(c.fuel_added) AS total_fuel
   FROM calculations c
     JOIN employees e ON c.operator_id = e.id
  WHERE c.work_date >= '2026-04-01'::date AND c.work_date <= '2026-04-30'::date
  GROUP BY e.id, e.last_name, e.first_name, e.middle_name;


-- public.operator_monthly_stats_05_26 исходный текст

CREATE OR REPLACE VIEW public.operator_monthly_stats_05_26
AS WITH base_data AS (
         SELECT drilling_operations.operator_id,
            drilling_operations.holes_count,
            drilling_operations.meters_drilled,
            drilling_operations.fuel_added,
            drilling_operations.work_date,
            drilling_operations.rig_id,
            drilling_operations.engine_hours_end,
            lag(drilling_operations.engine_hours_end) OVER (PARTITION BY drilling_operations.rig_id ORDER BY drilling_operations.engine_hours_end) AS engine_hours_start
           FROM drilling_operations
        ), calculations AS (
         SELECT base_data.operator_id,
            base_data.holes_count,
            base_data.meters_drilled,
            base_data.fuel_added,
            base_data.work_date,
            base_data.rig_id,
            base_data.engine_hours_end,
            base_data.engine_hours_start,
            base_data.engine_hours_end - base_data.engine_hours_start AS shift_hours
           FROM base_data
        )
 SELECT (((e.last_name || ' '::text) || "left"(e.first_name, 1)) || '.'::text) ||
        CASE
            WHEN e.middle_name IS NOT NULL THEN "left"(e.middle_name, 1) || '.'::text
            ELSE ''::text
        END AS operator_fio,
    count(*) AS shifts_worked,
    sum(c.holes_count) AS total_holes,
    sum(c.meters_drilled) AS total_meters,
    sum(
        CASE
            WHEN c.shift_hours > 0::numeric THEN c.shift_hours
            ELSE 0::numeric
        END) AS total_engine_hours,
    round(sum(c.meters_drilled) / NULLIF(sum(
        CASE
            WHEN c.shift_hours > 0::numeric THEN c.shift_hours
            ELSE 0::numeric
        END), 0::numeric), 2) AS meters_per_hour,
    sum(c.fuel_added) AS total_fuel
   FROM calculations c
     JOIN employees e ON c.operator_id = e.id
  WHERE c.work_date >= '2026-05-01'::date AND c.work_date <= '2026-05-31'::date
  GROUP BY e.id, e.last_name, e.first_name, e.middle_name;


-- public.operator_monthly_stats_universal исходный текст

CREATE OR REPLACE VIEW public.operator_monthly_stats_universal
AS WITH base_data AS (
         SELECT drilling_operations.operator_id,
            drilling_operations.holes_count,
            drilling_operations.meters_drilled,
            drilling_operations.fuel_added,
            drilling_operations.work_date,
            drilling_operations.rig_id,
            drilling_operations.engine_hours_end,
            date_trunc('month'::text, drilling_operations.work_date::timestamp with time zone) AS month_period,
            lag(drilling_operations.engine_hours_end) OVER (PARTITION BY drilling_operations.rig_id ORDER BY drilling_operations.work_date, drilling_operations.engine_hours_end) AS engine_hours_start
           FROM drilling_operations
        ), calculations AS (
         SELECT base_data.operator_id,
            base_data.holes_count,
            base_data.meters_drilled,
            base_data.fuel_added,
            base_data.work_date,
            base_data.rig_id,
            base_data.engine_hours_end,
            base_data.month_period,
            base_data.engine_hours_start,
            COALESCE(
                CASE
                    WHEN base_data.engine_hours_end > base_data.engine_hours_start THEN base_data.engine_hours_end - base_data.engine_hours_start
                    ELSE 0::numeric
                END, 0::numeric) AS shift_hours
           FROM base_data
        )
 SELECT c.month_period,
    to_char(c.month_period, 'Month YYYY'::text) AS month_name,
    (((e.last_name || ' '::text) || "left"(e.first_name, 1)) || '.'::text) ||
        CASE
            WHEN e.middle_name IS NOT NULL THEN "left"(e.middle_name, 1) || '.'::text
            ELSE ''::text
        END AS operator_fio,
    count(*) AS shifts_worked,
    sum(c.holes_count) AS total_holes,
    sum(c.meters_drilled) AS total_meters,
    sum(c.shift_hours) AS total_engine_hours,
    round(sum(c.meters_drilled) / NULLIF(sum(c.shift_hours), 0::numeric), 2) AS meters_per_hour,
    sum(c.fuel_added) AS total_fuel
   FROM calculations c
     JOIN employees e ON c.operator_id = e.id
  GROUP BY c.month_period, e.id, e.last_name, e.first_name, e.middle_name
  ORDER BY c.month_period DESC, (sum(c.meters_drilled)) DESC;


-- public.v_drilling_final_stats исходный текст

CREATE OR REPLACE VIEW public.v_drilling_final_stats
AS WITH base_data AS (
         SELECT ops.id,
            ops.work_date,
            ops.shift,
            ops.site_id,
            ops.operator_id,
            ops.rig_id,
            ops.holes_count,
            ops.meters_drilled,
            ops.engine_hours_end,
            ops.fuel_added,
            ops.fuel_supplier_id,
            ops.created_at,
            ops.block_num,
            lag(ops.engine_hours_end) OVER (PARTITION BY ops.rig_id ORDER BY ops.work_date, ops.created_at) AS engine_hours_start
           FROM drilling_operations ops
        )
 SELECT b.id,
    b.work_date,
    b.shift,
    b.site_id,
    b.operator_id,
    (((e.last_name || ' '::text) || "left"(e.first_name, 1)) || '.'::text) ||
        CASE
            WHEN e.middle_name IS NOT NULL THEN "left"(e.middle_name, 1) || '.'::text
            ELSE ''::text
        END AS operator_fio,
    b.rig_id,
    b.holes_count,
    b.meters_drilled,
    b.engine_hours_end,
    b.fuel_added,
    b.fuel_supplier_id,
    b.created_at,
    b.block_num,
    b.engine_hours_start,
    GREATEST(0::numeric, b.engine_hours_end - COALESCE(b.engine_hours_start, b.engine_hours_end)) AS shift_hours
   FROM base_data b
     JOIN employees e ON b.operator_id = e.id;


-- public.v_explosive_unit_costs исходный текст

CREATE OR REPLACE VIEW public.v_explosive_unit_costs
AS WITH delivery_ratio AS (
         SELECT s_1.id AS spec_id,
            s_1.total_delivery_cost_no_vat / NULLIF(sum(i_1.quantity_ordered * i_1.price_per_unit_no_vat), 0::numeric) AS delivery_factor
           FROM explosive_purchase_specs s_1
             JOIN explosive_spec_items i_1 ON s_1.id = i_1.spec_id
          GROUP BY s_1.id, s_1.total_delivery_cost_no_vat
        )
 SELECT t.name AS product_name,
    i.unit_name,
    round(i.price_per_unit_no_vat * (1::numeric + dr.delivery_factor) / i.conversion_factor, 2) AS cost_per_item_no_vat,
    s.spec_number,
    s.spec_date
   FROM explosive_spec_items i
     JOIN explosive_purchase_specs s ON i.spec_id = s.id
     JOIN initiating_device_types t ON i.device_type_id = t.id
     JOIN delivery_ratio dr ON s.id = dr.spec_id;



-- DROP FUNCTION public.rls_auto_enable();

CREATE OR REPLACE FUNCTION public.rls_auto_enable()
 RETURNS event_trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table','partitioned table')
  LOOP
     IF cmd.schema_name IS NOT NULL AND cmd.schema_name IN ('public') AND cmd.schema_name NOT IN ('pg_catalog','information_schema') AND cmd.schema_name NOT LIKE 'pg_toast%' AND cmd.schema_name NOT LIKE 'pg_temp%' THEN
      BEGIN
        EXECUTE format('alter table if exists %s enable row level security', cmd.object_identity);
        RAISE LOG 'rls_auto_enable: enabled RLS on %', cmd.object_identity;
      EXCEPTION
        WHEN OTHERS THEN
          RAISE LOG 'rls_auto_enable: failed to enable RLS on %', cmd.object_identity;
      END;
     ELSE
        RAISE LOG 'rls_auto_enable: skip % (either system schema or not in enforced list: %.)', cmd.object_identity, cmd.schema_name;
     END IF;
  END LOOP;
END;
$function$
;