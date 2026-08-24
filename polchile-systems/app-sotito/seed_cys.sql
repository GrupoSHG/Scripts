-- ============================================================
-- Datos maestros CyS — zonas (centros de costo) y trabajadores
-- Fuente: Facturacion_Intercompany_CyS_1.xlsx (hoja Parámetros)
-- ============================================================

insert into centros_costo (codigo, nombre, factura_a, activo) values
  ('CYS-BUIN',     'Buin',            'Sergio Reyes',    true),
  ('CYS-ELTABO',   'El Tabo',         'Jefe Starken',    true),
  ('CYS-JARDIN',   'Jardín',          'Jardín',          true),
  ('CYS-CODEGUA',  'Codegua',         'Rafael Diez',     true),
  ('CYS-POLCHILE', 'Polchile',        'Polchile',        true),
  ('CYS-LOSPALTOS','Los Paltos (LP)', 'Polchile',        true),
  ('CYS-STARKEN',  'Starken',         'EXCLUIDA',        true);

insert into personas (nombre, tarifa_diaria, activo) values
  ('Ivan Soto',              45000, true),
  ('Alfonso Lauquen',        41000, true),
  ('Francisco Lauquen',      41000, true),
  ('Byron Silva',            33500, true),
  ('Sebastian Lauquen',      30000, true),
  ('Demian Concha',          30000, true),
  ('Ricardo Chacon',         32500, true);
