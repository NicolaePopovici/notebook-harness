# Databricks notebook source
# MAGIC %md
# MAGIC # Cash app

# COMMAND ----------

# DBTITLE 1,Config
TOL = 0.01
SRC = "/mnt/raw/receipts"

# COMMAND ----------

from pyspark.sql import functions as F

r = spark.read.parquet(SRC)
i = spark.table("fin.open_invoices").filter(F.col("st") == "O")

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TEMP VIEW m AS
# MAGIC SELECT r.rid, i.iid, r.amt
# MAGIC FROM r JOIN i ON r.ref = i.inv_no
# MAGIC WHERE abs(r.amt - i.amt) <= 0.01

# COMMAND ----------

x = spark.table("m").dropDuplicates(["rid"])
x.write.mode("overwrite").saveAsTable("fin.allocations")
